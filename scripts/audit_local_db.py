import sqlite3

db_path = "db.sqlite3"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== DEVEDORES COM UUID_ACESSO ===")
cursor.execute("SELECT id, nome, uuid_acesso FROM nucleo_devedor LIMIT 10;")
devedores = cursor.fetchall()
for row in devedores:
    print(f"ID: {row[0]} | Nome: {row[1]} | UUID: {row[2]}")

print("\n=== ACORDOS ATIVOS ===")
cursor.execute("""
    SELECT a.id, a.numero_acordo, a.status, a.modalidade, d.nome 
    FROM nucleo_acordo a 
    JOIN nucleo_devedor d ON a.devedor_id = d.id
    WHERE a.status != 'CANCELADO'
    LIMIT 10;
""")
acordos = cursor.fetchall()
for row in acordos:
    print(f"Acordo #{row[1]} | Status: {row[2]} | Modalidade: {row[3]} | Devedor: {row[4]}")

print("\n=== ALERTAS FINANCEIROS ===")
cursor.execute("SELECT status, COUNT(*) FROM nucleo_alertafinanceiro GROUP BY status;")
alertas = cursor.fetchall()
for row in alertas:
    print(f"Status: {row[0]} | QTD: {row[1]}")

print("\n=== AUDITORIA (Últimas 5 entradas) ===")
cursor.execute("SELECT acao, detalhes, data_hora FROM nucleo_registroauditoria ORDER BY data_hora DESC LIMIT 5;")
audit = cursor.fetchall()
for row in audit:
    print(f"[{row[2]}] {row[0]}: {row[1][:80]}")

conn.close()
