# CNA Finanças - Guia de Deploy (Coolify)

Este repositório foi preparado para deploy automático no Coolify usando Docker.

## 📋 Variáveis de Ambiente Necessárias

No painel do Coolify, configure as seguintes variáveis:

| Variável | Valor/Exemplo | Descrição |
| :--- | :--- | :--- |
| `SECRET_KEY` | `sua-chave-ultra-secreta` | Chave única para segurança do Django. |
| `DEBUG` | `False` | Deve ser False em produção. |
| `ALLOWED_HOSTS` | `www.cnacob.moysesnet.com` | Domínio(s) autorizados. |
| `CSRF_TRUSTED_ORIGINS` | `https://www.cnacob.moysesnet.com` | Origens confiáveis para proteção CSRF (HTTPS). |
| `PORTAL_BASE_URL` | `https://www.cnacob.moysesnet.com` | URL base para links enviados aos devedores. |
| `DATABASE_URL` | `sqlite:///app/db.sqlite3` | Caminho do banco de dados (Volume recomendado). |

## 💾 Persistência de Dados (SQLite)

Como o projeto usa SQLite, é **obrigatório** configurar um **Volume** no Coolify:
- **Source**: `cna-db-data` (ou nome de sua preferência)
- **Destination**: `/app/db.sqlite3`

Isso garante que os dados não sejam apagados a cada novo deploy.

## 🛡️ Backup do Banco de Dados

Criei um script de backup em `scripts/backup_db.py`. 

### Como executar manualmente:
No terminal da aplicação no Coolify:
```bash
python scripts/backup_db.py
```
O script salvará o backup na pasta `/app/backups/` e manterá apenas os últimos 7 arquivos.

---

## ✅ Checklist Pós-Deploy

1. Acesse `https://www.cnacob.moysesnet.com/login/`
2. Verifique se o CSS/Imagens estão carregando (Whitenoise + SSL).
3. Tente realizar um login operacional.
4. Verifique a página de Dashboard para garantir que as queries financeiras estão OK.
