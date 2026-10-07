# Relatórios de revisão do HollyOCR

## HollyOCR 5.0.1, build 4 — 2 de outubro de 2026

### Resultado

O código foi atualizado, o aplicativo foi recompilado e a instalação em `/Applications/HollyOCR.app` foi substituída pela versão 5.0.1, build 4. A janela do aplicativo instalado foi aberta e conferida, exibindo a versão correta, Apple Vision automático e disponibilidade de Poppler e Tesseract.

### Falhas corrigidas

- Combinação nativa/OCR: as heurísticas de similaridade eliminavam linhas que continham valores, datas, nomes ou negações diferentes. A deduplicação agora exige correspondência entre linhas ou blocos completos, preservando associações, sinais e separadores numéricos.
- Integridade PDF: a extração de menos páginas que as existentes, a renderização incompleta e falhas de OCR podiam resultar em sucesso. Essas condições agora impedem a geração de uma saída apresentada como completa. Um extrator que falha depois de emitir páginas não reinicia o documento por outro mecanismo, evitando duplicações e deslocamento da numeração.
- Retomada: falhas de OCR preservam as páginas concluídas no checkpoint. O formato do checkpoint foi atualizado para invalidar resultados obtidos pelas regras anteriores.
- DOCX: parágrafos e tabelas eram separados, alterando a ordem de leitura; tabelas aninhadas e tabelas de cabeçalhos/rodapés não eram extraídas. A leitura agora percorre os blocos na ordem original, preserva colunas vazias e evita duplicações em células mescladas e cabeçalhos vinculados.
- Interface e cancelamento: o fechamento aguarda o encerramento do processamento; seletores continuam restritos após cada conversão; agrupamento é persistido; cancelamentos não anunciam conclusão nem levam a barra a 100% artificialmente. Ctrl+C na CLI retorna código 130.
- Validação OCR: o mecanismo selecionado é considerado, inclusive Tesseract explícito quando Vision está disponível; idiomas combinados são conferidos separadamente.
- Compilação: a ferramenta de limpeza já existia dentro de `.venv`; foi acrescentada uma alternativa que preserva os artefatos em `.build_backups/` quando ela está ausente.

### Atualizações do ambiente

- Python e Tk: 3.12.15. O novo aplicativo incorpora o Python atualizado. A [publicação oficial do Python](https://www.python.org/downloads/release/python-31215/) documenta correções de segurança, incluindo exaustão de memória na descompressão de arquivos ZIP.
- Poppler: 26.09.0, com [correções oficiais para PDFs malformados](https://poppler.freedesktop.org/).
- Tesseract: 5.5.3, conforme a [publicação oficial](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3).
- As versões fixadas dos pacotes Python foram preservadas após auditoria. A atualização Homebrew também atualizou dependências compartilhadas necessárias e o dependente `ffmpeg@7`; os pacotes anteriores foram preservados sem limpeza automática.

### Validação

- 79 testes e 15 subtestes aprovados no ambiente Python 3.12.15.
- Pyflakes, Ruff e verificação de diferenças sem erros; Bandit sem achados médios ou altos.
- `pip check` sem dependências inconsistentes; `pip-audit` sem vulnerabilidades conhecidas nos 34 pacotes fixados, na consulta desta data.
- Testes funcionais repetidos no binário compilado e no aplicativo instalado: PDF nativo de duas páginas, PDF escaneado de duas páginas com processos paralelos, PDF misto com valores/datas/nomes/negação divergentes, imagem, DOCX e Markdown; geração de auditoria por página; Apple Vision e Tesseract; preservação da imagem original e ausência de sobrescrita de conversões anteriores.
- Bundle Mach-O arm64; assinatura ad hoc verificada com `codesign --verify --deep --strict`; tamanho de 112.312 KB. Os arquivos do bundle instalado correspondem integralmente aos do build validado.
- Digest SHA-256 da árvore do build: `e28dc512dec554a26ee2328133a993994bf310893e536fad3f12ac0557d73907`.
- Backup da instalação anterior: `.build_backups/installed_20261002_190942/HollyOCR.app`.

### Limites da validação

Os testes funcionais usaram documentos sintéticos locais. A assinatura permanece ad hoc e Poppler/Tesseract continuam dependências externas. Esta revisão não gerou nem validou executáveis Windows ou Linux.

## HollyOCR 5.0.0 — revisão anterior

Data: 8 de agosto de 2026
Plataforma principal: macOS 27, Apple Silicon arm64, Python 3.12

### Escopo

A revisão cobriu organização do projeto, identidade, segurança de arquivos, dependências, extração PDF, OCR, interface, linha de comando, versionamento, empacotamento e compatibilidade futura.

### Correções principais

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

### Dependências

Foram atualizados, entre outros:

- `pypdf` 6.15.0;
- `Pillow` 12.3.0;
- `setuptools` 84.0.0;
- `PyMuPDF`, `pymupdf4llm` e `pymupdf-layout` 1.28.2;
- `PyInstaller` 6.22.0.

O `pip-audit` não encontrou vulnerabilidades conhecidas no arquivo de dependências fixadas após as atualizações.

### Validação automatizada

- 44 testes aprovados;
- Pyflakes sem erros;
- Ruff sem erros críticos de sintaxe/importação e Bandit sem achados médios ou altos;
- dependências consistentes segundo `pip check`;
- entrada `python -m hollyocr` compilada e importável;
- testes de regressão para preservação de imagens, exclusão segura, Apple Vision, OCR híbrido, checkpoints e medição de imagens PDF.

### Aplicativo macOS gerado

- nome: `HollyOCR.app`;
- arquitetura: Mach-O arm64 nativo;
- versão embutida: 5.0.0, build 1;
- bundle identifier: `com.thiagoalbuquerque.hollyocr`;
- assinatura ad hoc verificada com `codesign --verify --deep --strict`;
- tamanho: 116.952 KB;
- digest SHA-256 da árvore: `5a421ecc31fe2cec6a4c43a2153fa918ff0a37413622ffebb95f131f5b193a03`.

### Compatibilidade

- macOS Apple Silicon: plataforma principal, com Apple Vision e fallback Tesseract.
- Windows: código e receita PyInstaller existentes; o executável deve ser validado em Windows.
- Linux: núcleo testado na integração contínua; requer Tk, Poppler e Tesseract instalados.

### Limitações

- OCR não garante precisão total em imagens borradas, inclinadas, comprimidas ou com texto muito pequeno.
- Poppler e Tesseract são dependências externas no macOS.
- O build público para macOS ainda exige assinatura Developer ID e notarização.
- Builds de Windows e Linux não foram validados nesta máquina macOS.
