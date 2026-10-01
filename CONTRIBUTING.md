# Guia de Contribuição — TrainingHub

Este documento define o fluxo de desenvolvimento utilizado pela equipe do TrainingHub.

O objetivo é manter o repositório organizado, facilitar a colaboração entre os integrantes e evitar alterações diretas ou instáveis na branch principal.

## 1. Fluxo de desenvolvimento

Toda alteração deve estar relacionada a uma Issue do Jira.

O fluxo padrão é:

Jira Issue
→ Branch
→ Desenvolvimento
→ Commits
→ Push
→ Pull Request
→ GitHub Actions
→ Code Review
→ Merge na main
→ Issue concluída no Jira

## 2. Branch principal

A branch `main` representa a versão integrada e estável do projeto.

Não desenvolver funcionalidades diretamente na `main`.

Antes de iniciar uma nova tarefa:

```bash
git checkout main
git pull origin main
```

Depois, criar uma branch específica para a Issue.

## 3. Padrão de branches

Formato:

```text
tipo/TH-XX-descricao
```

Tipos utilizados:

- `feature/` — nova funcionalidade
- `fix/` — correção
- `docs/` — documentação
- `test/` — testes
- `devops/` — infraestrutura e CI/CD
- `refactor/` — refatoração

Exemplos:

```text
feature/TH-19-usuario
feature/TH-20-perfil
feature/TH-21-interface-web
devops/TH-22-github-actions
docs/TH-23-fluxo-git
```

## 4. Padrão de commits

Formato:

```text
TH-XX tipo: descrição
```

Tipos principais:

- `feat` — nova funcionalidade
- `fix` — correção
- `docs` — documentação
- `test` — testes
- `refactor` — refatoração
- `ci` — integração contínua
- `chore` — manutenção ou configuração

Exemplos:

```text
TH-19 feat: implement user repository
TH-20 feat: implement profile service
TH-21 feat: create responsive admin layout
TH-22 ci: configure build workflow
TH-23 docs: document Git workflow
```

Os commits devem ser pequenos e representar alterações relacionadas.

## 5. Pull Requests

Após concluir uma tarefa:

```bash
git add .
git commit -m "TH-XX tipo: descricao"
git push -u origin nome-da-branch
```

Depois, abrir um Pull Request da branch da tarefa para `main`.

O Pull Request deve:

- informar a Issue `TH-XX`;
- explicar resumidamente o que foi alterado;
- informar como a alteração foi testada;
- estar livre de conflitos;
- compilar corretamente;
- passar pelo GitHub Actions quando o CI estiver disponível.

## 6. Revisão de código

O autor da alteração não deve ser o único responsável por revisar seu próprio código.

Sempre que possível, pelo menos outro integrante deve revisar o Pull Request antes do merge.

Durante a revisão, verificar:

- funcionamento da implementação;
- organização do código;
- arquitetura do projeto;
- possíveis erros;
- impacto sobre funcionalidades existentes;
- presença de arquivos que não deveriam ser versionados.

## 7. Atualização da branch

Caso a `main` receba alterações enquanto uma tarefa está sendo desenvolvida, atualizar a branch antes de finalizar o Pull Request.

```bash
git checkout main
git pull origin main

git checkout nome-da-branch
git merge main
```

Resolver eventuais conflitos localmente, testar novamente e realizar o push.

## 8. Resolução de conflitos

Ao ocorrer um conflito:

1. Identificar os arquivos conflitantes.
2. Analisar as duas versões antes de remover qualquer código.
3. Resolver manualmente o conflito.
4. Compilar e testar o projeto.
5. Adicionar os arquivos corrigidos.
6. Criar o commit da resolução.
7. Fazer push novamente.

Nunca remover alterações de outro integrante sem entender o impacto.

Em caso de dúvida, conversar com o responsável pelo código antes de resolver o conflito.

## 9. Arquivos que não devem ser versionados

Não adicionar ao Git:

- diretório `build/`;
- executáveis;
- DLLs geradas;
- arquivos objeto;
- banco SQLite local;
- arquivos `.env`;
- configurações pessoais da IDE;
- arquivos temporários.

Consultar `.gitignore` antes de adicionar novos tipos de arquivos.

## 10. Responsabilidade da equipe

Todos os integrantes são responsáveis por manter a `main` funcional.

Antes de abrir um Pull Request:

- atualizar a branch;
- compilar o projeto;
- executar os testes disponíveis;
- verificar os arquivos modificados;
- garantir que apenas alterações relacionadas à Issue estejam incluídas.

O objetivo deste fluxo é permitir que diferentes módulos do TrainingHub sejam desenvolvidos em paralelo sem comprometer a estabilidade do projeto.