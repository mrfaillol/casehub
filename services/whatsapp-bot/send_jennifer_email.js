const { Resend } = require("resend");

const resendApiKey = process.env.RESEND_API_KEY;
if (!resendApiKey) throw new Error("RESEND_API_KEY environment variable is required");
const resend = new Resend(resendApiKey);

async function sendEmail() {
  try {
    const result = await resend.emails.send({
      from: `${process.env.ORG_NAME || "CaseHub"} <${process.env.NOTIFICATION_EMAIL || "notifications@casehub.app"}>`,
      to: "jnascimento207@gmail.com",
      cc: (process.env.ORG_EMAIL || "info@casehub.app"),
      subject: "Re: Help with Brazilian passport/name change",
      html: `
<p>Hi Jennifer,</p>

<p>Thank you for reaching out to us, and I understand the complexity of managing documentation as a dual citizen!</p>

<p>Our law firm specializes exclusively in <strong>U.S. immigration matters</strong> (visas, green cards, work permits, etc.), so we would not be the right fit to assist with Brazilian passport renewal, name changes with Brazil, or citizenship registration for your children.</p>

<p>For your specific needs, I recommend contacting the <strong>Brazilian Consulate</strong> that serves your area. They handle:</p>
<ul>
  <li>Passport renewal (even with name changes due to marriage)</li>
  <li>Name change registration (averbação de casamento)</li>
  <li>Children's citizenship registration (registro de nascimento)</li>
</ul>

<p>You can find your nearest consulate here: <a href="https://www.gov.br/mre/pt-br/assuntos/portal-consular">https://www.gov.br/mre/pt-br/assuntos/portal-consular</a></p>

<p>If you or your family ever need assistance with U.S. immigration matters in the future, please don't hesitate to reach out - we would be happy to help!</p>

<p>Respectfully,<br>
${process.env.ORG_NAME || "CaseHub"} Team</p>
      `
    });
    console.log("Email enviado:", JSON.stringify(result));
  } catch (error) {
    console.error("Erro:", error.message);
  }
}

sendEmail();
