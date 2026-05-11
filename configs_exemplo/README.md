# Configurações SAFX Editor — Pasta de Exemplos

Esta pasta contém exemplos de arquivos de configuração para o **SAFX Editor**.

## Como usar

### Exportar configurações atuais
1. Abra o SAFX Editor
2. Menu **Arquivo → Exportar Configurações...**
3. Escolha onde salvar o arquivo `.json`

### Importar configurações
1. Abra o SAFX Editor
2. Menu **Arquivo → Importar Configurações...**
3. Selecione um arquivo `.json` de configuração
4. Reinicie o aplicativo para aplicar todas as mudanças

## Arquivo de exemplo

### `config_exemplo.json`
Demonstra a estrutura completa do arquivo de configuração, incluindo:

| Seção | Descrição |
|---|---|
| `general` | Tema, tamanho de fonte, paginação, caminho dos layouts |
| `export` | Destino padrão, encoding, quebra de linha |
| `sftp_profiles` | Lista de perfis SFTP (múltiplos servidores/clientes) |
| `db_profiles` | Lista de conexões de banco de dados externos |
| `ui` | Preferências de interface (tema, largura da sidebar) |

## Casos de uso

### Configuração por cliente
Crie um arquivo `.json` por cliente com suas configurações específicas:
- SFTP do cliente
- Banco de dados do sistema ERP do cliente
- Diretório de layouts personalizado

### Backup de configurações
Antes de reinstalar ou migrar para outra máquina, exporte suas configurações e importe no novo ambiente.

### Time de analistas
Distribua um arquivo de configuração padrão da empresa para toda a equipe importar.
