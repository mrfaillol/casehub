/**
 * Structured Logger - WhatsApp Bot
 * Wraps pino for JSON-structured logging with request tracing
 *
 * Usage:
 *   const logger = require('./services/logger');
 *   logger.info({ phone: '5511...', source: 'main-handler' }, 'Message received');
 *   logger.error({ err, phone }, 'Failed to send');
 *
 * All logs include: timestamp, level, pid, hostname
 * Business logs should include: phone, source, action
 */

const pino = require('pino');

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  transport: process.env.NODE_ENV === 'development' ? {
    target: 'pino/file',
    options: { destination: 1 } // stdout
  } : undefined,
  formatters: {
    level(label) {
      return { level: label };
    }
  },
  base: {
    service: 'whatsapp-bot',
    version: '2.0.0'
  },
  timestamp: pino.stdTimeFunctions.isoTime
});

// Convenience child loggers for subsystems
const child = (module) => logger.child({ module });

module.exports = logger;
module.exports.child = child;
