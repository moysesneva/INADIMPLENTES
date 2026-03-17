
import sys
import os

# View verification instead of runtime authenticated request
views_path = 'nucleo/views.py'
export_path = 'nucleo/services/export.py'

if os.path.exists(views_path):
    with open(views_path, 'r', encoding='utf-8') as f:
        content = f.read()
        if 'export.generate_excel_response' in content and 'export.generate_csv_response' in content:
            print("Views are correctly calling export services.")
        else:
            print("ERROR: Views not properly calling export services.")
else:
    print(f"ERROR: {views_path} not found.")

if os.path.exists(export_path):
    with open(export_path, 'r', encoding='utf-8') as f:
        content = f.read()
        if "content_type='text/csv'" in content and "content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'" in content:
            print("Export services have correct content types.")
        else:
            print("ERROR: Export services have incorrect content types.")
else:
    print(f"ERROR: {export_path} not found.")
