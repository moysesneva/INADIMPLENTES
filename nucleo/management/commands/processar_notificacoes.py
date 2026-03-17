from django.core.management.base import BaseCommand
from ...services.notificacao import processar_motor_regras, processar_alertas_comunicacao

class Command(BaseCommand):
    help = 'Executa o motor de regras e o disparador de alertas para envio de cobranças'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('--- Início Processamento de Notificações ---'))
        
        # Fluxo 1: Motor de Regras (Baseado em Status)
        self.stdout.write(self.style.NOTICE('Processando motor de regras clássico...'))
        qtd_regras, erros_regras = processar_motor_regras()
        
        # Fluxo 2: Disparador de Alertas (Fase G2)
        self.stdout.write(self.style.NOTICE('Processando disparador de alertas financeiros...'))
        qtd_alertas, erros_alertas = processar_alertas_comunicacao()
        
        # Sumário
        total = qtd_regras + qtd_alertas
        if total > 0:
            self.stdout.write(self.style.SUCCESS(f'Sucesso Total: {total} notificações ({qtd_regras} regras, {qtd_alertas} alertas).'))
        else:
            self.stdout.write(self.style.WARNING('Nenhuma notificação elegível encontrada.'))
            
        todos_erros = erros_regras + erros_alertas
        if todos_erros:
            for erro in todos_erros:
                self.stdout.write(self.style.ERROR(f'Erro: {erro}'))
        
        self.stdout.write(self.style.NOTICE('--- Processamento Finalizado ---'))
