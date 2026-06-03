/**
 * Email Module - WhatsApp Bot
 * CaseHub
 * v2.0 - Usando Resend (mais confiavel)
 */

const { Resend } = require('resend');

const appConfig = require("./config");
const EMAIL_CONFIG = {
  resendApiKey: appConfig.email.resendApiKey,
  fromEmail: '${process.env.NOTIFICATION_EMAIL || "notifications@casehub.app"}',
  fromName: '${process.env.ORG_NAME || "CaseHub"} Bot',
  notifyEmails: [(process.env.CENTER_EMAIL || 'center@casehub.app')]
};

let resend = null;

/**
 * Inicializar conexao
 */
function init() {
  try {
    resend = new Resend(EMAIL_CONFIG.resendApiKey);
    console.log('[EMAIL] Resend inicializado');
    return true;
  } catch (error) {
    console.error('[EMAIL] Erro ao inicializar Resend:', error.message);
    return false;
  }
}

/**
 * Gerar sugestoes de horarios (proximos 3 dias uteis)
 */
function generateTimeSlots() {
  const slots = [];
  const now = new Date();

  for (let i = 1; i <= 5; i++) {
    const date = new Date(now);
    date.setDate(date.getDate() + i);

    // Pular fim de semana
    if (date.getDay() === 0 || date.getDay() === 6) continue;

    const dateStr = date.toLocaleDateString('pt-BR', {
      weekday: 'long',
      day: '2-digit',
      month: '2-digit'
    });

    slots.push({ display: `${dateStr} - 10:00 AM EST`, value: `${date.toISOString().split('T')[0]}T10:00` });
    slots.push({ display: `${dateStr} - 2:00 PM EST`, value: `${date.toISOString().split('T')[0]}T14:00` });
    slots.push({ display: `${dateStr} - 4:00 PM EST`, value: `${date.toISOString().split('T')[0]}T16:00` });

    if (slots.length >= 6) break;
  }

  return slots;
}

/**
 * Enviar email de nova lead
 */
async function sendNewLeadEmail(leadData) {
  if (!resend) init();

  try {
    const name = leadData.client_name || leadData.whatsapp_name || 'Nao informado';
    const phone = leadData.phone || 'N/A';
    const interest = leadData.visa_interest || 'Nao informado';
    const email = leadData.email || 'Nao informado';
    const source = leadData.source || 'WhatsApp';
    const score = leadData.lead_score || 'N/A';
    const status = leadData.lead_status || 'N/A';

    const subject = `🆕 Nova Lead: ${name} | Score: ${score}`;

    const html = `
      <h2>Nova Lead Recebida</h2>

      <table style="border-collapse: collapse; width: 100%;">
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Nome:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${name}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Telefone:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${phone}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Email:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${email}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Interesse:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${interest}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Origem:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${source}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Score:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${score}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Status:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${status}</td>
        </tr>
      </table>

      <p style="margin-top: 20px; color: #666;">
        Esta notificacao foi gerada automaticamente pelo WhatsApp Bot.
      </p>
    `;

    const result = await resend.emails.send({
      from: `${EMAIL_CONFIG.fromName} <${EMAIL_CONFIG.fromEmail}>`,
      to: EMAIL_CONFIG.notifyEmails,
      subject: subject,
      html: html
    });

    console.log('[EMAIL] Nova lead enviado:', result.id || result);
    return { success: true, id: result.id };

  } catch (error) {
    console.error('[EMAIL] Erro ao enviar nova lead:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Enviar email de consulta gratuita
 */
async function sendFreeConsultationRequest(leadData) {
  if (!resend) init();

  try {
    const name = leadData.client_name || 'Cliente';
    const phone = leadData.phone || 'N/A';
    const email = leadData.email || 'N/A';
    const interest = leadData.visa_interest || 'Nao informado';
    const slots = generateTimeSlots();

    const subject = `📅 Consulta Gratuita Solicitada: ${name}`;

    const slotsHtml = slots.map((slot, i) => `<li>${slot.display}</li>`).join('');

    const html = `
      <h2>Consulta Gratuita Solicitada</h2>

      <table style="border-collapse: collapse; width: 100%;">
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Nome:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${name}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Telefone:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${phone}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Email:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${email}</td>
        </tr>
        <tr>
          <td style="padding: 8px; border: 1px solid #ddd;"><strong>Interesse:</strong></td>
          <td style="padding: 8px; border: 1px solid #ddd;">${interest}</td>
        </tr>
      </table>

      <h3>Sugestoes de Horarios:</h3>
      <ul>
        ${slotsHtml}
      </ul>

      <p style="margin-top: 20px; color: #666;">
        Por favor, entre em contato para confirmar o agendamento.
      </p>
    `;

    const result = await resend.emails.send({
      from: `${EMAIL_CONFIG.fromName} <${EMAIL_CONFIG.fromEmail}>`,
      to: EMAIL_CONFIG.notifyEmails,
      subject: subject,
      html: html
    });

    console.log('[EMAIL] Consulta gratuita enviado:', result.id || result);
    return { success: true, id: result.id, slots: slots };

  } catch (error) {
    console.error('[EMAIL] Erro ao enviar consulta:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Enviar email de lead urgente
 */
async function sendUrgentLeadEmail(leadData) {
  if (!resend) init();

  try {
    const name = leadData.client_name || 'Cliente';
    const phone = leadData.phone || 'N/A';

    const subject = `🚨 URGENTE: ${name} - Atencao Imediata Necessaria`;

    const html = `
      <h2 style="color: red;">⚠️ LEAD URGENTE</h2>

      <p><strong>Nome:</strong> ${name}</p>
      <p><strong>Telefone:</strong> ${phone}</p>

      <p style="color: red; font-weight: bold;">
        Este cliente indicou urgencia. Por favor, entre em contato imediatamente.
      </p>
    `;

    const result = await resend.emails.send({
      from: `${EMAIL_CONFIG.fromName} <${EMAIL_CONFIG.fromEmail}>`,
      to: EMAIL_CONFIG.notifyEmails,
      subject: subject,
      html: html
    });

    console.log('[EMAIL] Lead urgente enviado:', result.id || result);
    return { success: true, id: result.id };

  } catch (error) {
    console.error('[EMAIL] Erro ao enviar urgente:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Enviar email de lead qualificada pelo Intake Form
 */
async function sendQualifiedIntakeEmail(leadData) {
  if (!resend) init();

  try {
    const name = leadData.client_name || 'Cliente';
    const phone = leadData.phone || 'N/A';
    const email = leadData.email || 'N/A';
    const score = leadData.score || 0;
    const pathway = leadData.pathway || 'unknown';
    const summary = leadData.summary || '';

    // Nomes amigaveis dos pathways
    const pathwayNames = {
      'family_based': 'Family-Based (Green Card via familia)',
      'employment_based': 'Employment-Based (Green Card via trabalho)',
      'humanitarian_asylum': 'Humanitarian - Asilo',
      'humanitarian_vawa': 'Humanitarian - VAWA',
      'humanitarian_u_visa': 'Humanitarian - U-Visa',
      'humanitarian_t_visa': 'Humanitarian - T-Visa',
      'humanitarian_sijs': 'Humanitarian - SIJS',
      'investor': 'Investor Visa',
      'unknown': 'A determinar'
    };

    const pathwayDisplay = pathwayNames[pathway] || pathway;

    // Determinar cor do score
    let scoreColor = '#28a745'; // verde
    if (score < 80) scoreColor = '#ffc107'; // amarelo
    if (score < 70) scoreColor = '#dc3545'; // vermelho

    const subject = `🎯 LEAD QUALIFICADA (Score ${score}): ${name}`;

    const html = `
      <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 10px;">
          🎯 Lead Qualificada pelo Intake Form
        </h2>

        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
          <h3 style="margin-top: 0;">Dados do Cliente</h3>
          <table style="border-collapse: collapse; width: 100%;">
            <tr>
              <td style="padding: 8px; border: 1px solid #ddd;"><strong>Nome:</strong></td>
              <td style="padding: 8px; border: 1px solid #ddd;">${name}</td>
            </tr>
            <tr>
              <td style="padding: 8px; border: 1px solid #ddd;"><strong>Telefone:</strong></td>
              <td style="padding: 8px; border: 1px solid #ddd;">${phone}</td>
            </tr>
            <tr>
              <td style="padding: 8px; border: 1px solid #ddd;"><strong>Email:</strong></td>
              <td style="padding: 8px; border: 1px solid #ddd;">${email}</td>
            </tr>
          </table>
        </div>

        <div style="background: #e7f5ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
          <h3 style="margin-top: 0;">Avaliacao do Intake Form</h3>
          <table style="border-collapse: collapse; width: 100%;">
            <tr>
              <td style="padding: 8px; border: 1px solid #ddd;"><strong>Score:</strong></td>
              <td style="padding: 8px; border: 1px solid #ddd;">
                <span style="font-size: 24px; font-weight: bold; color: ${scoreColor};">${score}/100</span>
              </td>
            </tr>
            <tr>
              <td style="padding: 8px; border: 1px solid #ddd;"><strong>Pathway:</strong></td>
              <td style="padding: 8px; border: 1px solid #ddd;">${pathwayDisplay}</td>
            </tr>
            <tr>
              <td style="padding: 8px; border: 1px solid #ddd;"><strong>Status:</strong></td>
              <td style="padding: 8px; border: 1px solid #ddd;">
                <span style="background: #28a745; color: white; padding: 4px 8px; border-radius: 4px;">
                  QUALIFICADO PARA CONSULTA GRATUITA
                </span>
              </td>
            </tr>
          </table>
        </div>

        ${summary ? `
        <div style="background: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0;">
          <h3 style="margin-top: 0;">Resumo da Analise</h3>
          <pre style="white-space: pre-wrap; font-family: monospace; font-size: 12px;">${summary}</pre>
        </div>
        ` : ''}

        <div style="background: #d4edda; padding: 15px; border-radius: 8px; margin: 20px 0; text-align: center;">
          <p style="margin: 0; font-weight: bold;">
            ✅ O cliente recebeu o link do Calendly para agendar consulta gratuita
          </p>
        </div>

        <p style="margin-top: 20px; color: #666; font-size: 12px;">
          Esta notificacao foi gerada automaticamente pelo WhatsApp Bot ao completar o Intake Form.
        </p>
      </div>
    `;

    const result = await resend.emails.send({
      from: `${EMAIL_CONFIG.fromName} <${EMAIL_CONFIG.fromEmail}>`,
      to: EMAIL_CONFIG.notifyEmails,
      subject: subject,
      html: html
    });

    console.log('[EMAIL] Lead qualificada intake enviado:', result.id || result);
    return { success: true, id: result.id };

  } catch (error) {
    console.error('[EMAIL] Erro ao enviar lead qualificada intake:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Enviar email generico (para lead-monitor)
 */
async function sendEmail(options) {
  if (!resend) init();

  try {
    const { to, subject, html, text } = options;

    const data = await resend.emails.send({
      from: `${EMAIL_CONFIG.fromName} <${EMAIL_CONFIG.fromEmail}>`,
      to: Array.isArray(to) ? to : [to],
      subject: subject,
      html: html || text || ''
    });

    console.log('[EMAIL] Email enviado para', to);
    return { success: true, data };
  } catch (error) {
    console.error('[EMAIL] Erro ao enviar email:', error.message);
    return { success: false, error: error.message };
  }
}

module.exports = {
  EMAIL_CONFIG,
  init,
  generateTimeSlots,
  sendNewLeadEmail,
  sendFreeConsultationRequest,
  sendUrgentLeadEmail,
  sendQualifiedIntakeEmail,
  sendEmail
};
