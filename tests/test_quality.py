import unittest

from hollyocr.core.quality import (
    analyze_page_text_quality,
    choose_best_page_text,
    merge_native_and_ocr_text,
)


class FaithfulMergeTests(unittest.TestCase):
    def test_near_duplicates_keep_changed_facts(self):
        cases = (
            (
                "Valor da parcela mensal R$ 1000,00 com vencimento no dia 10.",
                "Valor da parcela mensal R$ 1900,00 com vencimento no dia 10.",
            ),
            (
                "A entrega ocorreu em 12/09/2026 para destinatário João Silva.",
                "A entrega ocorreu em 13/09/2026 para destinatário João Silva.",
            ),
            (
                "O pedido não foi recebido pelo consumidor em nenhuma oportunidade.",
                "O pedido foi recebido pelo consumidor em nenhuma oportunidade.",
            ),
            (
                "Não autorizo o pagamento da parcela.",
                "Autorizo o pagamento da parcela.",
            ),
            (
                "O pedido foi recebido pelo consumidor, não.",
                "O pedido foi recebido pelo consumidor.",
            ),
            (
                "Destinatário da entrega do produto: João da Silva Santos.",
                "Destinatário da entrega do produto: José da Silva Santos.",
            ),
        )
        for native, ocr in cases:
            with self.subTest(ocr=ocr):
                merged, source, _ = choose_best_page_text(
                    native,
                    analyze_page_text_quality(native),
                    ocr,
                    analyze_page_text_quality(ocr),
                    preserve_both=True,
                )
                self.assertEqual(source, "nativo+ocr")
                self.assertIn(native, merged)
                self.assertIn(ocr, merged)

    def test_numeric_signs_and_separators_are_significant(self):
        cases = (
            ("Saldo da conta R$ 1000,00", "Saldo da conta R$ -1000,00"),
            ("Número do documento: 100/2026", "Número do documento: 10/02026"),
            ("Valor registrado: 1,000", "Valor registrado: 1.000"),
            ("Taxa contratada: 15", "Taxa contratada: 15%"),
        )
        for native, ocr in cases:
            with self.subTest(ocr=ocr):
                merged = merge_native_and_ocr_text(native, ocr)
                self.assertIn(native, merged)
                self.assertIn(ocr, merged)

    def test_identifier_and_name_prefixes_are_not_duplicates(self):
        cases = (
            ("Destinatário Anabela", "Destinatário Ana"),
            ("Documento número ABCDE1234", "Documento número ABCDE123"),
        )
        for native, ocr in cases:
            with self.subTest(ocr=ocr):
                self.assertIn(ocr, merge_native_and_ocr_text(native, ocr))

    def test_fragmented_table_keeps_reordered_amounts(self):
        native = "Produto quantidade valor saldo data prazo total situação 100,00 200,00"
        ocr = "\n".join(native.split()[:-2] + ["200,00", "100,00"])
        merged = merge_native_and_ocr_text(native, ocr)
        self.assertIn(ocr, merged)

    def test_additional_fragmented_table_keeps_repeated_amounts(self):
        native = "Descrição nativa de outro documento anexado aos autos."
        ocr = "Produto A\n100,00\nProduto B\n100,00"
        self.assertIn(ocr, merge_native_and_ocr_text(native, ocr))

    def test_fragmented_ocr_cannot_omit_initial_negation(self):
        native = "Não autorizo o pagamento de qualquer parcela deste contrato sem aprovação."
        ocr = "\n".join(native.split()[1:])
        self.assertIn(ocr, merge_native_and_ocr_text(native, ocr))

    def test_exact_duplicate_and_wrapped_text_are_deduplicated(self):
        native = "Esta é uma manifestação longa do processo que foi\nquebrada pela camada nativa."
        ocr = "Esta e uma manifestacao longa do processo que foi quebrada pela camada nativa."
        self.assertEqual(merge_native_and_ocr_text(native, ocr), native)

    def test_fragmented_table_with_same_sequence_is_deduplicated(self):
        native = "data lançamentos valor saldo 86,62 509,60 8,84 0,17 823,52 116,57"
        self.assertEqual(merge_native_and_ocr_text(native, "\n".join(native.split())), native)


if __name__ == "__main__":
    unittest.main()
