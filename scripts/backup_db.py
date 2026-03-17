import os
import shutil
from datetime import datetime
from pathlib import Path

def backup_sqlite():
    # Caminhos baseados na estrutura do Docker/Coolify
    base_dir = Path(__file__).resolve().parent.parent
    db_path = base_dir / "db.sqlite3"
    backup_dir = base_dir / "backups"
    
    # Cria diretório de backup se não existir
    backup_dir.mkdir(exist_ok=True)
    
    if not db_path.exists():
        print(f"Erro: Banco de dados não encontrado em {db_path}")
        return

    # Nome do arquivo com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"db_backup_{timestamp}.sqlite3"
    
    try:
        shutil.copy2(db_path, backup_file)
        print(f"Backup realizado com sucesso: {backup_file}")
        
        # Limpeza: Mantém apenas os últimos 7 backups
        all_backups = sorted(backup_dir.glob("*.sqlite3"), key=os.path.getmtime)
        if len(all_backups) > 7:
            for old_backup in all_backups[:-7]:
                old_backup.unlink()
                print(f"Backup antigo removido: {old_backup.name}")
                
    except Exception as e:
        print(f"Erro ao realizar backup: {str(e)}")

if __name__ == "__main__":
    backup_sqlite()
