import csv
from datetime import datetime
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font

def generate_csv_response(queryset, filename_prefix="export"):
    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    response['Content-Disposition'] = f'attachment; filename={filename_prefix}_{timestamp}.csv'
    
    # UTF-8 BOM for Excel
    response.write('\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    
    # Header
    if queryset.model.__name__ == 'Acordo':
        headers = ['ID', 'Nº Acordo', 'Devedor', 'CPF', 'Valor Total', 'Status', 'Data Acordo']
        writer.writerow(headers)
        for obj in queryset:
            writer.writerow([
                obj.id,
                obj.numero_acordo,
                obj.devedor.nome,
                obj.devedor.cpf,
                f"{obj.valor_total:.2f}".replace('.', ','),
                obj.get_status_display(),
                obj.data_acordo.strftime('%d/%m/%Y') if obj.data_acordo else ''
            ])
    elif queryset.model.__name__ == 'Devedor':
        headers = ['ID', 'Nome', 'CPF', 'E-mail', 'Telefone', 'Cidade', 'UF']
        writer.writerow(headers)
        for obj in queryset:
            writer.writerow([
                obj.id,
                obj.nome,
                obj.cpf,
                obj.email,
                obj.telefone,
                obj.cidade,
                obj.uf
            ])
            
    return response

def generate_excel_response(queryset, filename_prefix="export"):
    wb = Workbook()
    ws = wb.active
    ws.title = queryset.model._meta.verbose_name_plural.title()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename={filename_prefix}_{timestamp}.xlsx'
    
    if queryset.model.__name__ == 'Acordo':
        headers = ['ID', 'Nº Acordo', 'Devedor', 'CPF', 'Valor Total', 'Status', 'Data Acordo']
        ws.append(headers)
        for obj in queryset:
            ws.append([
                obj.id,
                obj.numero_acordo,
                obj.devedor.nome,
                obj.devedor.cpf,
                float(obj.valor_total),
                obj.get_status_display(),
                obj.data_acordo.strftime('%d/%m/%Y') if obj.data_acordo else ''
            ])
    elif queryset.model.__name__ == 'Devedor':
        headers = ['ID', 'Nome', 'CPF', 'E-mail', 'Telefone', 'Cidade', 'UF']
        ws.append(headers)
        for obj in queryset:
            ws.append([
                obj.id,
                obj.nome,
                obj.cpf,
                obj.email,
                obj.telefone,
                obj.cidade,
                obj.uf
            ])

    # Bold headers
    for cell in ws[1]:
        cell.font = Font(bold=True)
        
    wb.save(response)
    return response
