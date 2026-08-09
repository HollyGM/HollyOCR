# Relatório de revisão — HollyOCR 5.0.0

Data: 8 de agosto de 2026
Plataforma principal: macOS 27, Apple Silicon arm64, Python 3.12

## Escopo

A revisão cobriu organização do projeto, identidade, segurança de arquivos, dependências, extração PDF, OCR, interface, linha de comando, versionamento, empacotamento e compatibilidade futura.

## Correções principais

- O projeto e o pacote foram renomeados para `HollyOCR` e `hollyocr`.
- A identidade jurídica, o monograma anterior, a paleta dourada e textos ligados à advocacia foram removidos.
- A versão passou a ter uma fonte canônica e foi definida como 5.0.0, build 1.
- A exclusão de imagens após OCR agora é desativada por padrão e restrita à pasta temporária do sistema.
- O redirecionamento de erros do Apple Vision deixou de tentar continuar duas vezes quando o código chamado lança uma exceção.
- A configuração é gravada de forma atômica e com permissão restrita no macOS/Linux; preferências antigas são migradas e credenciais obsoletas são eliminadas.
- Parâmetros numéricos da CLI receberam limites explícitos para impedir valores negativos ou consumo absurdo de recursos.
- A interface passou a apresentar somente valores de DPI realmente aceitos pelo pipeline.
- A abertura de arquivos usa executáveis nativos resolvidos e não invoca shell.
- `PyPDF2` foi substituído por `pypdf`. A adaptação à API atual preserva a medição da área das imagens embutidas.

## Dependências

Foram atualizados, entre outros:

- `pypdf` 6.15.0;
- `Pillow` 12.3.0;
- `setuptools` 84.0.0;
- `PyMuPDF`, `pymupdf4llm` e `pymupdf-layout` 1.28.2;
- `PyInstaller` 6.22.0.

O `pip-audit` não encontrou vulnerabilidades conhecidas no arquivo de dependências fixadas após as atualizações.

## Validação automatizada

- 44 testes aprovados;
- Pyflakes sem erros;
- Ruff sem erros críticos de sintaxe/importação e Bandit sem achados médios ou altos;
- dependências consistentes segundo `pip check`;
- entrada `python -m hollyocr` compilada e importável;
- testes de regressão para preservação de imagens, exclusão segura, Apple Vision, OCR híbrido, checkpoints e medição de imagens PDF.

## Aplicativo macOS gerado

- nome: `HollyOCR.app`;
- arquitetura: Mach-O arm64 nativo;
- versão embutida: 5.0.0, build 1;
- bundle identifier: `com.thiagoalbuquerque.hollyocr`;
- assinatura ad hoc verificada com `codesign --verify --deep --strict`;
- tamanho: 116.952 KB;
- digest SHA-256 da árvore: `5a421ecc31fe2cec6a4c43a2153fa918ff0a37413622ffebb95f131f5b193a03`.

## Compatibilidade

- macOS Apple Silicon: plataforma principal, com Apple Vision e fallback Tesseract.
- Windows: código e receita PyInstaller existentes; o executável deve ser validado em Windows.
- Linux: núcleo testado na integração contínua; requer Tk, Poppler e Tesseract instalados.

## Limitações

- OCR não garante precisão total em imagens borradas, inclinadas, comprimidas ou com texto muito pequeno.
- Poppler e Tesseract são dependências externas no macOS.
- O build público para macOS ainda exige assinatura Developer ID e notarização.
- Builds de Windows e Linux não foram validados nesta máquina macOS.
