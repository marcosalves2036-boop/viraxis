"""Serviço de envio de email via Resend API."""

import logging
from typing import Any

import httpx

from viraxis.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS = "Viraxis <onboarding@resend.dev>"


async def _send(to: str, subject: str, html: str) -> bool:
    """Envia email via Resend. Retorna True se OK."""
    api_key = getattr(settings, "resend_api_key", "")
    if not api_key:
        logger.warning("RESEND_API_KEY não configurada — email não enviado para %s", to)
        return False

    payload: dict[str, Any] = {
        "from": FROM_ADDRESS,
        "to": [to],
        "subject": subject,
        "html": html,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code in (200, 201):
            logger.info("Email enviado para %s | subject=%s", to, subject)
            return True
        logger.error("Resend erro %s: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.error("Falha ao enviar email para %s: %s", to, exc)
        return False


def _verification_html(full_name: str, verify_url: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0f0f0f;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#1a1a1a;border-radius:12px;overflow:hidden">
        <!-- Header -->
        <tr><td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px;text-align:center">
          <h1 style="color:#fff;margin:0;font-size:28px;font-weight:700;letter-spacing:-0.5px">Viraxis</h1>
          <p style="color:#c4b5fd;margin:8px 0 0;font-size:14px">Plataforma de Conteúdo com IA</p>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:40px 32px">
          <h2 style="color:#f5f5f5;margin:0 0 16px;font-size:20px">Olá, {full_name}! 👋</h2>
          <p style="color:#a3a3a3;margin:0 0 24px;line-height:1.6;font-size:15px">
            Seu cadastro na Viraxis foi criado com sucesso.<br>
            Clique no botão abaixo para verificar seu email e ativar sua conta.
          </p>
          <div style="text-align:center;margin:32px 0">
            <a href="{verify_url}"
               style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                      color:#fff;text-decoration:none;padding:14px 36px;border-radius:8px;
                      font-weight:600;font-size:15px;letter-spacing:0.3px">
              Verificar meu email
            </a>
          </div>
          <p style="color:#737373;font-size:13px;margin:24px 0 0;line-height:1.5">
            O link expira em <strong style="color:#a3a3a3">24 horas</strong>.<br>
            Se você não criou uma conta na Viraxis, ignore este email.
          </p>
        </td></tr>
        <!-- Footer -->
        <tr><td style="padding:20px 32px;border-top:1px solid #2a2a2a;text-align:center">
          <p style="color:#525252;font-size:12px;margin:0">
            © 2026 Viraxis · Todos os direitos reservados
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


async def send_verification_email(to: str, full_name: str, token: str) -> bool:
    """Envia email de verificação de conta."""
    frontend_url = getattr(settings, "frontend_url", "https://viraxis.com.br")
    verify_url = f"{frontend_url}/verify-email?token={token}"
    html = _verification_html(full_name, verify_url)
    return await _send(to, "Verifique seu email — Viraxis", html)


async def send_password_reset_email(to: str, full_name: str, token: str) -> bool:
    """Envia email de redefinição de senha."""
    frontend_url = getattr(settings, "frontend_url", "https://viraxis.com.br")
    reset_url = f"{frontend_url}/reset-password?token={token}"
    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:40px 16px;background:#0f0f0f;font-family:'Segoe UI',Arial,sans-serif">
  <div style="max-width:560px;margin:0 auto;background:#1a1a1a;border-radius:12px;overflow:hidden">
    <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px;text-align:center">
      <h1 style="color:#fff;margin:0;font-size:28px">Viraxis</h1>
    </div>
    <div style="padding:40px 32px">
      <h2 style="color:#f5f5f5;margin:0 0 16px">Redefinição de senha</h2>
      <p style="color:#a3a3a3;line-height:1.6">Olá, {full_name}.<br>Recebemos uma solicitação para redefinir sua senha.</p>
      <div style="text-align:center;margin:32px 0">
        <a href="{reset_url}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;text-decoration:none;padding:14px 36px;border-radius:8px;font-weight:600">
          Redefinir senha
        </a>
      </div>
      <p style="color:#737373;font-size:13px">Link válido por 1 hora. Se não foi você, ignore este email.</p>
    </div>
  </div>
</body>
</html>
"""
    return await _send(to, "Redefinição de senha — Viraxis", html)
