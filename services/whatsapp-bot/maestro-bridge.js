/**
 * Maestro v5 - WhatsApp Bridge (Thin Client)
 * Forwards messages from WhatsApp Bot to Maestro API.
 * Replaces all 8 maestro-*.js files with a single ~50 line bridge.
 *
 * Usage in server.js:
 *   const maestroBridge = require('./maestro-bridge');
 *   // In message handler:
 *   const maestroResponse = await maestroBridge.handleMessage(phone, message);
 *   if (maestroResponse) { await sendWhatsApp(phone, maestroResponse); return; }
 */

const MAESTRO_URL = process.env.MAESTRO_URL || 'http://localhost:8020';
const MAESTRO_API_KEY = process.env.MAESTRO_API_KEY || '';

/**
 * Forward a message to Maestro API and get response.
 * Returns response text if Maestro handled it, null otherwise.
 */
async function handleMessage(phone, message) {
    try {
        const res = await fetch(`${MAESTRO_URL}/api/v1/whatsapp/message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Api-Key': MAESTRO_API_KEY,
            },
            body: JSON.stringify({
                phone: phone,
                message: message,
                timestamp: new Date().toISOString(),
            }),
        });

        if (!res.ok) {
            console.log(`[MaestroBridge] API error: ${res.status}`);
            return null;
        }

        const data = await res.json();

        // If Maestro didn't handle the message, return null
        // so the bot continues its normal flow
        if (!data.handled) {
            return null;
        }

        return data.response || null;
    } catch (err) {
        console.error(`[MaestroBridge] Connection error: ${err.message}`);
        return null;
    }
}

/**
 * Check if Maestro API is reachable.
 */
async function isAvailable() {
    try {
        const res = await fetch(`${MAESTRO_URL}/api/v1/health`, {
            timeout: 3000,
        });
        return res.ok;
    } catch {
        return false;
    }
}

module.exports = { handleMessage, isAvailable };
