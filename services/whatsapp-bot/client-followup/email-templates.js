/**
 * Email Templates for Client Follow-up System
 * CaseHub
 * v1.0
 */

/**
 * Generate Weekly Follow-up Email HTML
 */
function getWeeklyEmailHTML(clientName) {
  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Weekly Check-in - ${process.env.ORG_NAME || "CaseHub"}</title>
  <style>
    body {
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.6;
      color: #333333;
      margin: 0;
      padding: 0;
      background-color: #f5f5f5;
    }
    .container {
      max-width: 600px;
      margin: 0 auto;
      background-color: #ffffff;
      padding: 40px;
    }
    .header {
      border-bottom: 3px solid #2c5282;
      padding-bottom: 20px;
      margin-bottom: 30px;
    }
    .logo {
      color: #2c5282;
      font-size: 24px;
      font-weight: bold;
      margin: 0;
    }
    .content {
      margin-bottom: 30px;
    }
    .content p {
      margin: 0 0 16px 0;
      color: #333333;
    }
    .signature {
      margin-top: 30px;
    }
    .signature p {
      margin: 0 0 8px 0;
    }
    .footer {
      border-top: 1px solid #e2e8f0;
      padding-top: 20px;
      margin-top: 30px;
      font-size: 12px;
      color: #718096;
    }
    .footer a {
      color: #2c5282;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 class="logo">${process.env.ORG_NAME || "CaseHub"}</h1>
    </div>
    <div class="content">
      <p>Dear ${clientName},</p>
      <p>We hope you are doing well.</p>
      <p>This is a brief weekly check-in to see if you have any questions or need any assistance at this time. Our team remains available and happy to support you with anything you may need.</p>
      <p>Please feel free to reach out at your convenience.</p>
      <div class="signature">
        <p>Warm regards,</p>
        <p><strong>${process.env.ORG_NAME || "CaseHub"}</strong></p>
      </div>
    </div>
    <div class="footer">
      <p>${process.env.ORG_NAME || "CaseHub"}</p>
      <p>Email: <a href="mailto:${process.env.ORG_EMAIL || "info@casehub.app"}">${process.env.ORG_EMAIL || "info@casehub.app"}</a></p>
      <p>Website: <a href=(process.env.ORG_WEBSITE || "https://casehub.app")>${process.env.ORG_WEBSITE || "casehub.app"}</a></p>
    </div>
  </div>
</body>
</html>
  `.trim();
}

/**
 * Generate Monthly Follow-up Email HTML
 */
function getMonthlyEmailHTML(clientName) {
  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Monthly Follow-up - ${process.env.ORG_NAME || "CaseHub"}</title>
  <style>
    body {
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.6;
      color: #333333;
      margin: 0;
      padding: 0;
      background-color: #f5f5f5;
    }
    .container {
      max-width: 600px;
      margin: 0 auto;
      background-color: #ffffff;
      padding: 40px;
    }
    .header {
      border-bottom: 3px solid #2c5282;
      padding-bottom: 20px;
      margin-bottom: 30px;
    }
    .logo {
      color: #2c5282;
      font-size: 24px;
      font-weight: bold;
      margin: 0;
    }
    .content {
      margin-bottom: 30px;
    }
    .content p {
      margin: 0 0 16px 0;
      color: #333333;
    }
    .signature {
      margin-top: 30px;
    }
    .signature p {
      margin: 0 0 8px 0;
    }
    .footer {
      border-top: 1px solid #e2e8f0;
      padding-top: 20px;
      margin-top: 30px;
      font-size: 12px;
      color: #718096;
    }
    .footer a {
      color: #2c5282;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 class="logo">${process.env.ORG_NAME || "CaseHub"}</h1>
    </div>
    <div class="content">
      <p>Dear ${clientName},</p>
      <p>We hope this message finds you well.</p>
      <p>As part of our monthly follow-up, we would like to check in to see if you have any questions, concerns, or if there is anything we can assist you with regarding your case.</p>
      <p>Please do not hesitate to contact us if you need any clarification or support.</p>
      <div class="signature">
        <p>Warm regards,</p>
        <p><strong>${process.env.ORG_NAME || "CaseHub"}</strong></p>
      </div>
    </div>
    <div class="footer">
      <p>${process.env.ORG_NAME || "CaseHub"}</p>
      <p>Email: <a href="mailto:${process.env.ORG_EMAIL || "info@casehub.app"}">${process.env.ORG_EMAIL || "info@casehub.app"}</a></p>
      <p>Website: <a href=(process.env.ORG_WEBSITE || "https://casehub.app")>${process.env.ORG_WEBSITE || "casehub.app"}</a></p>
    </div>
  </div>
</body>
</html>
  `.trim();
}

/**
 * Get plain text version of weekly email
 */
function getWeeklyEmailText(clientName) {
  return `Dear ${clientName},

We hope you are doing well.

This is a brief weekly check-in to see if you have any questions or need any assistance at this time. Our team remains available and happy to support you with anything you may need.

Please feel free to reach out at your convenience.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}

---
Email: ${process.env.ORG_EMAIL || "info@casehub.app"}
Website: ${process.env.ORG_WEBSITE || "https://casehub.app"}`;
}

/**
 * Get plain text version of monthly email
 */
function getMonthlyEmailText(clientName) {
  return `Dear ${clientName},

We hope this message finds you well.

As part of our monthly follow-up, we would like to check in to see if you have any questions, concerns, or if there is anything we can assist you with regarding your case.

Please do not hesitate to contact us if you need any clarification or support.

Warm regards,
${process.env.ORG_NAME || "CaseHub"}

---
Email: ${process.env.ORG_EMAIL || "info@casehub.app"}
Website: ${process.env.ORG_WEBSITE || "https://casehub.app"}`;
}

/**
 * Get email subject for follow-up type
 */
function getEmailSubject(type) {
  if (type === 'weekly') {
    return 'Weekly Check-in - ${process.env.ORG_NAME || "CaseHub"}';
  } else if (type === 'monthly') {
    return 'Monthly Follow-up - ${process.env.ORG_NAME || "CaseHub"}';
  }
  return '${process.env.ORG_NAME || "CaseHub"}';
}

/**
 * Generate email content for a follow-up type
 */
function generateEmail(type, clientName) {
  const name = clientName || 'Valued Client';

  if (type === 'weekly') {
    return {
      subject: getEmailSubject('weekly'),
      html: getWeeklyEmailHTML(name),
      text: getWeeklyEmailText(name)
    };
  } else if (type === 'monthly') {
    return {
      subject: getEmailSubject('monthly'),
      html: getMonthlyEmailHTML(name),
      text: getMonthlyEmailText(name)
    };
  }

  throw new Error(`Unknown follow-up type: ${type}`);
}

module.exports = {
  getWeeklyEmailHTML,
  getMonthlyEmailHTML,
  getWeeklyEmailText,
  getMonthlyEmailText,
  getEmailSubject,
  generateEmail
};
