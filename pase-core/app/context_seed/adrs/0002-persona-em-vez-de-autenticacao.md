# ADR-0002: Persona em vez de autenticação

**Estado:** aceita (válida enquanto o app for local)

## Contexto
O FinTrack é uma prova de conceito local, com duas pessoas fictícias. Um login real exigiria
senha, sessão, recuperação de conta e proteção de rotas, sem acrescentar valor à prova.

## Decisão
A pessoa **escolhe uma persona** na entrada, e o `id` fica no navegador. A tela diz
explicitamente que não é autenticação.

## Consequências
- Qualquer pessoa pode ver os dados de qualquer persona.
- Não se acrescenta auth "por precaução": isso daria a impressão de que o app está pronto
  para exposição.
- Estado que depende da persona precisa reagir à troca de persona.

## Quando rever
Antes de qualquer exposição pública ou uso com dados reais. Ver `security-and-compliance`.
