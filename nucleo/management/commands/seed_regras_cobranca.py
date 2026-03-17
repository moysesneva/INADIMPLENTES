from django.core.management.base import BaseCommand
from nucleo.models import RegraCobranca
from decimal import Decimal

class Command(BaseCommand):
    help = "Semeia as regras de cobrança padrão (DIRETA_CNA, SERASA, FEIRAO_SERASA) de forma idempotente."

    def handle(self, *args, **kwargs):
        regras = [
            {
                "modalidade": "DIRETA_CNA",
                "dias_atraso_minimo": 0,
                "limite_desconto_juros_multa": Decimal("50.00"),
                "percentual_entrada_minima": Decimal("10.00"),
                "parcelas_maximas": 4,
                "ativa": True,
            },
            {
                "modalidade": "SERASA",
                "dias_atraso_minimo": 0,
                "limite_desconto_juros_multa": Decimal("80.00"),
                "percentual_entrada_minima": Decimal("40.00"),
                "parcelas_maximas": 4,
                "ativa": True,
            },
            {
                "modalidade": "FEIRAO_SERASA",
                "dias_atraso_minimo": 0,
                "limite_desconto_juros_multa": Decimal("100.00"),
                "percentual_entrada_minima": Decimal("45.00"),
                "parcelas_maximas": 4,
                "ativa": True,
            },
        ]

        self.stdout.write(self.style.SUCCESS("Iniciando o seeding de RegraCobranca..."))

        for dados in regras:
            obj, created = RegraCobranca.objects.update_or_create(
                modalidade=dados["modalidade"],
                dias_atraso_minimo=dados["dias_atraso_minimo"],
                defaults={
                    "limite_desconto_juros_multa": dados["limite_desconto_juros_multa"],
                    "percentual_entrada_minima": dados["percentual_entrada_minima"],
                    "parcelas_maximas": dados["parcelas_maximas"],
                    "ativa": dados["ativa"],
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f"Regra criada: {obj.modalidade} (Atraso Min: {obj.dias_atraso_minimo})"))
            else:
                self.stdout.write(self.style.WARNING(f"Regra atualizada: {obj.modalidade} (Atraso Min: {obj.dias_atraso_minimo})"))

        self.stdout.write(self.style.SUCCESS("Seeding concluído com sucesso."))
