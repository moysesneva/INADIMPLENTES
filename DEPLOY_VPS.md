# Deploy CNA Inadimplentes - VPS Ubuntu

## 1. Preparação do VPS

### 1.1 Conecte ao VPS
```bash
ssh root@IP_DO_SEU_VPS
```

### 1.2 Atualize o sistema
```bash
apt update && apt upgrade -y
```

### 1.3 Instale Docker e Docker Compose
```bash
# Instalar Docker
curl -fsSL https://get.docker.com | sh

# Instalar Docker Compose
apt install docker-compose -y

# Adicionar usuário ao grupo docker (opcional)
usermod -aG docker $USER

# Habilitar Docker
systemctl enable docker
```

### 1.4 Verifique a instalação
```bash
docker --version
docker-compose --version
```

---

## 2. Transferir Arquivos para o VPS

### Opção A: Via Git (Recomendado)
```bash
# No seu VPS
apt install git -y
git clone https://SEU_REPOSITORIO.git /app
cd /app
```

### Opção B: Via SCP
```bash
# No seu computador local
scp -r ./cna_inadimplentes root@IP_DO_VPS:/app
```

---

## 3. Configurar Variáveis de Ambiente

```bash
cd /app

# Copie o arquivo de exemplo
cp .env.example .env

# Edite o arquivo com suas configurações
nano .env
```

**Edite estas variáveis no `.env`:**
```
SECRET_KEY=GERE UMA CHAVE ÚNICA EM https://djecrety.ir/
DEBUG=False
ALLOWED_HOSTS=www.cnacob.moysesnet.com,cnacob.moysesnet.com
CSRF_TRUSTED_ORIGINS=https://www.cnacob.moysesnet.com
PORTAL_BASE_URL=https://www.cnacob.moysesnet.com
```

---

## 4. Configurar Firewall (UFW)

```bash
# Allow SSH (cuidado para não perder o acesso!)
ufw allow 22/tcp

# Allow HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Habilitar firewall
ufw enable
```

---

## 5. Build e Deploy com Docker

```bash
cd /app

# Build das imagens
docker-compose build

# Iniciar os serviços
docker-compose up -d

# Verificar logs
docker-compose logs -f
```

---

## 6. Configurar SSL com Certbot

### Instalar Certbot
```bash
apt install certbot python3-certbot-nginx -y
```

### Obter certificado SSL
```bash
# Primeiro, crie certificados temporários para o Nginx
# Edite temporariamente o nginx/conf.d/default.conf para não usar SSL

# Após criar os certificados, volte a configuração original
# e copie os certificados para nginx/ssl/

certbot certonly --nginx -d www.cnacob.moysesnet.com -d cnacob.moysesnet.com
```

### Copiar certificados
```bash
mkdir -p /app/nginx/ssl
cp /etc/letsencrypt/live/www.cnacob.moysesnet.com/fullchain.pem /app/nginx/ssl/
cp /etc/letsencrypt/live/www.cnacob.moysesnet.com/privkey.pem /app/nginx/ssl/
```

### Renovar automaticamente (Crontab)
```bash
# Edite o crontab
crontab -e

# Adicione esta linha para renewal diário
0 0 * * * certbot renew --quiet && docker-compose -f /app/docker-compose.yml restart nginx
```

---

## 7. Verificar Deployment

```bash
# Status dos containers
docker-compose ps

# Logs
docker-compose logs web

# Teste localmente
curl http://localhost/login/
```

---

## 8. Comandos Úteis

```bash
# Reiniciar aplicação
docker-compose restart

# Parar aplicação
docker-compose down

# Atualizar código
git pull origin main
docker-compose build
docker-compose up -d

# Backup do banco
docker-compose exec web python scripts/backup_db.py

# Ver uso de recursos
docker stats

# Acessar shell do container
docker-compose exec web bash
```

---

## 9. Solução de Problemas

### Container não inicia
```bash
docker-compose logs web
```

### Erro de permissão no banco
```bash
docker-compose exec web chown -R app:app /app
```

### SSL não funciona
```bash
# Verifique se os certificados existem
ls -la /app/nginx/ssl/

# Verifique logs do nginx
docker-compose logs nginx
```

### Problemas de conexão com banco
```bash
# Verifique se o volume existe
docker volume ls

# Recriar volume se necessário
docker-compose down -v
docker-compose up -d
```

---

## Checklist Pós-Deploy

- [ ] Acessar https://www.cnacob.moysesnet.com/login/
- [ ] Verificar se CSS/Imagens carregam
- [ ] Testar login com usuário admin
- [ ] Verificar Dashboard financeiro
- [ ] Testar Portal do Devedor
- [ ] Configurar backup automático
