# Como contribuir

1. Crie uma branch a partir de `main`.
2. Instale as dependências em um ambiente virtual Python 3.12.
3. Faça alterações pequenas e acompanhadas de testes.
4. Execute antes de enviar:

```bash
python -m pyflakes hollyocr tests
python -m pytest tests -q
python -m pip_audit -r requirements-macos-lock.txt
```

Não inclua documentos pessoais, arquivos convertidos, logs, credenciais, ambientes virtuais ou artefatos de build no repositório.
