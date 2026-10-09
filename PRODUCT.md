# Transcrição Local

<!-- impeccable:product-schema 1 -->

## Platform

macOS nativo, conforme pedido do usuário. Este projeto não é uma página web.

## Users

Usuário de Mac que transcreve mensagens de áudio no WhatsApp Web e quer
controlar o servidor local sem comandos de terminal.

## Product Purpose

Mostrar o estado real do servidor, iniciar e parar seu funcionamento e permitir
configurar separadamente seu início automático ao entrar no Mac.

## Operating Context

Interface com janela e ícone na barra de menus.
A extensão WA Plus a Mais é instalada e configurada separadamente no Chrome.

## Capabilities and Constraints

- Reutilizar a transcrição on-device da Apple, o conversor local e o endpoint existente.
- Preservar o endereço `http://127.0.0.1:5092/v1` e o modelo `apple-speechanalyzer`.
- Separar funcionamento atual do servidor e preferência de início automático.
- Oferecer teste local com áudio sintético, sem microfone ou gravações pessoais.
- Não salvar transcrições pessoais em logs nem usar fallback para a nuvem.
- Fechar a janela deve manter o ícone de menus; parar o servidor é uma ação explícita.
- Distribuição autocontida por `.dmg` para Apple Silicon e macOS 27, escolhida pelo usuário.
- O pacote compartilhável inclui runtime, conversor e áudio sintético, sem dados pessoais.
- Recursos permanecem no bundle; estado técnico fica na pasta de suporte do usuário.
- Modelos da Apple não acompanham o instalador: preparação explícita permite baixá-los uma vez.
- A extensão é instalada separadamente. A distribuição atual tem assinatura local, sem notarização Apple.

## Brand Commitments

Controles nativos do macOS e linguagem simples em português do Brasil.

## Evidence on Hand

Servidor, motor Swift e conversão local já testados com áudios sintéticos.
Os resultados da distribuição estão em `docs/verification-1.1.0.json`; não representam uma
validação de todas as condições de áudio real.
