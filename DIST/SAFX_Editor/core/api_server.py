"""
Servidor REST API embutido para o SAFX Editor.
Permite integração externa (leitura e atualização de dados) via HTTP.
Roda em thread separada para não bloquear a UI.

Endpoints:
  GET  /api/health               - status do servidor
  GET  /api/tables               - lista tabelas carregadas
  GET  /api/tables/{name}/schema - estrutura da tabela
  GET  /api/tables/{name}/data   - dados com filtros e paginação
  POST /api/tables/{name}/update - atualiza linhas via JSON
  GET  /api/tables/{name}/count  - total de registros
  POST /api/export/{name}        - dispara exportação da tabela
"""
import json
import logging
import threading
from typing import TYPE_CHECKING, Callable, Optional

logger = logging.getLogger(__name__)

_flask_available = False
try:
    from flask import Flask, jsonify, request, abort
    from flask_cors import CORS
    _flask_available = True
except ImportError:
    pass

if TYPE_CHECKING:
    from core.database import SAFXDatabase


class APIServer:
    """Servidor Flask embutido que expõe dados do SAFX via REST."""

    def __init__(self, db: "SAFXDatabase",
                 host: str = "0.0.0.0",
                 port: int = 8787,
                 api_key: str = "",
                 read_only: bool = False,
                 log_requests: bool = True,
                 on_update: Optional[Callable] = None):
        self.db = db
        self.host = host
        self.port = port
        self.api_key = api_key
        self.read_only = read_only
        self.log_requests = log_requests
        self.on_update = on_update  # callback para notificar a UI

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._app = None

    @property
    def available(self) -> bool:
        return _flask_available

    @property
    def running(self) -> bool:
        return self._running

    def _build_app(self):
        if not _flask_available:
            return None

        app = Flask("SAFXEditor")
        app.config["JSON_ENSURE_ASCII"] = False

        # CORS liberado para configurar via settings
        CORS(app)

        # Suprime logs do Flask no console
        if not self.log_requests:
            import logging as _log
            _log.getLogger("werkzeug").setLevel(_log.ERROR)

        db = self.db
        api_key = self.api_key
        read_only = self.read_only
        on_update = self.on_update

        def _check_auth():
            if api_key:
                key = request.headers.get("X-API-Key", "")
                if key != api_key:
                    abort(401, description="API Key inválida")

        # ─── Health ──────────────────────────────────────────────────────────
        @app.get("/api/health")
        def health():
            return jsonify({
                "status": "ok",
                "tables": db.get_loaded_tables(),
                "read_only": read_only,
                "version": "1.0",
                "product": "SAFX Editor — Adejo Desenvolvimento",
            })

        # ─── Tabelas ─────────────────────────────────────────────────────────
        @app.get("/api/tables")
        def list_tables():
            _check_auth()
            tables = db.get_loaded_tables()
            result = []
            for t in tables:
                try:
                    count = db.count_rows(t)
                    result.append({"name": t, "rows": count})
                except Exception:
                    result.append({"name": t, "rows": -1})
            return jsonify({"tables": result, "total": len(result)})

        @app.get("/api/tables/<table_name>/schema")
        def table_schema(table_name):
            _check_auth()
            info = db.get_schema_info(table_name)
            if not info:
                abort(404, description=f"Tabela '{table_name}' não encontrada")
            return jsonify({"table": table_name, "fields": info})

        @app.get("/api/tables/<table_name>/count")
        def table_count(table_name):
            _check_auth()
            filters = {k: v for k, v in request.args.items()
                       if k not in ("limit", "offset")}
            try:
                count = db.count_rows(table_name, filters or None)
                return jsonify({"table": table_name, "count": count,
                                "filters": filters})
            except Exception as e:
                abort(400, description=str(e))

        @app.get("/api/tables/<table_name>/data")
        def table_data(table_name):
            _check_auth()
            limit = int(request.args.get("limit", 1000))
            offset = int(request.args.get("offset", 0))
            limit = min(limit, 50000)  # limite de segurança

            filters = {k: v for k, v in request.args.items()
                       if k not in ("limit", "offset")}

            try:
                cols, rows = db.get_table_data(
                    table_name, filters or None, limit=limit, offset=offset)
                total = db.count_rows(table_name, filters or None)
                data = [dict(zip(cols, row)) for row in rows]
                return jsonify({
                    "table": table_name,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "returned": len(data),
                    "data": data,
                })
            except Exception as e:
                abort(400, description=str(e))

        # ─── Update ──────────────────────────────────────────────────────────
        @app.post("/api/tables/<table_name>/update")
        def table_update(table_name):
            _check_auth()
            if read_only:
                abort(403, description="Servidor em modo somente leitura")

            payload = request.get_json(silent=True)
            if not payload:
                abort(400, description="Body JSON esperado")

            # Formato: {"rows": [{"_row_id": 1, "CAMPO": "VALOR", ...}, ...]}
            rows = payload.get("rows", [])
            if not rows:
                abort(400, description="'rows' deve ser uma lista não vazia")

            updated = 0
            errors = []
            for row in rows:
                row_id = row.get("_row_id")
                if not row_id:
                    errors.append("Linha sem '_row_id' ignorada")
                    continue
                updates = [(int(row_id), field, str(val))
                           for field, val in row.items()
                           if field != "_row_id"]
                try:
                    n = db.update_cells_bulk(table_name, updates)
                    updated += n
                except Exception as e:
                    errors.append(str(e))

            if on_update:
                try:
                    on_update(table_name)
                except Exception:
                    pass

            return jsonify({
                "table": table_name,
                "updated_cells": updated,
                "errors": errors,
            })

        # ─── SQL direto ───────────────────────────────────────────────────────
        @app.post("/api/sql")
        def run_sql():
            _check_auth()
            payload = request.get_json(silent=True) or {}
            sql = payload.get("sql", "").strip()
            if not sql:
                abort(400, description="Campo 'sql' obrigatório")

            if read_only and not sql.upper().startswith("SELECT"):
                abort(403, description="Servidor em modo somente leitura — apenas SELECT")

            cols, rows, msg = db.execute_sql(sql)
            data = [dict(zip(cols, row)) for row in rows]
            return jsonify({
                "columns": cols,
                "rows": data,
                "message": msg,
                "count": len(data),
            })

        # ─── Erros formatados ─────────────────────────────────────────────────
        @app.errorhandler(400)
        @app.errorhandler(401)
        @app.errorhandler(403)
        @app.errorhandler(404)
        def handle_error(e):
            return jsonify({"error": str(e.description), "code": e.code}), e.code

        return app

    def start(self) -> tuple[bool, str]:
        """Inicia o servidor em thread daemon."""
        if not _flask_available:
            return False, ("Bibliotecas 'flask' e 'flask-cors' nao instaladas.\n"
                           "Execute: pip install flask flask-cors")
        if self._running:
            return True, f"API ja esta rodando em http://{self.host}:{self.port}"

        self._app = self._build_app()

        def _run():
            self._running = True
            try:
                self._app.run(
                    host=self.host,
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    threaded=True,
                )
            except Exception as e:
                logger.error(f"Erro no servidor API: {e}")
            finally:
                self._running = False

        self._thread = threading.Thread(target=_run, daemon=True,
                                        name="SAFXApiServer")
        self._thread.start()
        import time; time.sleep(0.8)

        if self._running:
            url = f"http://localhost:{self.port}"
            logger.info(f"API rodando em {url}")
            return True, (f"API iniciada com sucesso!\n"
                          f"URL Base: {url}/api/\n"
                          f"Documentacao: {url}/api/health\n"
                          f"Modo: {'Somente Leitura' if self.read_only else 'Leitura e Escrita'}")
        return False, f"Nao foi possivel iniciar a API na porta {self.port}"

    def stop(self):
        """Para o servidor (requer reinício do processo para limpeza total)."""
        self._running = False
        # Flask/Werkzeug nao tem shutdown limpo sem request context
        # Em producao use waitress ou gunicorn

    @classmethod
    def from_config(cls, db: "SAFXDatabase", cfg: dict,
                    on_update: Optional[Callable] = None) -> "APIServer":
        return cls(
            db=db,
            host=cfg.get("host", "0.0.0.0"),
            port=cfg.get("port", 8787),
            api_key=cfg.get("api_key", ""),
            read_only=cfg.get("read_only", False),
            log_requests=cfg.get("log_requests", True),
            on_update=on_update,
        )
