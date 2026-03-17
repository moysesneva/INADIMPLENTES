from django.core.management.base import BaseCommand
from nucleo.services.alertas import AlertasService

class Command(BaseCommand):
    help = 'Processa regras de negócio para geração de alertas financeiros proativos'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Iniciando detecção de riscos financeiros...'))
        
        resultados = AlertasService.processar_tudo()
        
        self.stdout.write(self.style.SUCCESS(
            f"Processamento concluído:\n"
            f"- Parcelas Atrasadas: {resultados['atrasadas']}\n"
            f"- Acordos em Risco: {resultados['em_risco']}\n"
            f"- Vencimentos Próximos: {resultados['proximos']}\n"
            f"- Quebras Identificadas: {resultados['quebras']}"
        ))
