/**
 * Media Handler - Download e processamento de arquivos via WhatsApp
 * CaseHub
 * v1.0 - Suporte a PDF, DOCX, imagens
 */

const fs = require('fs');
const path = require('path');

// Diretorio para salvar arquivos
const MEDIA_DIR = path.join(__dirname, 'media');

// Criar diretorio se nao existir
if (!fs.existsSync(MEDIA_DIR)) {
  fs.mkdirSync(MEDIA_DIR, { recursive: true });
  console.log('[MEDIA] Diretorio criado:', MEDIA_DIR);
}

// Tipos de arquivo aceitos para CV
const ACCEPTED_CV_TYPES = {
  'application/pdf': '.pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
  'application/msword': '.doc',
  'text/plain': '.txt'
};

// Tipos de imagem aceitos
const ACCEPTED_IMAGE_TYPES = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp'
};

// Mapa amplo mimetype -> extensão, cobrindo TODOS os tipos de mídia do
// WhatsApp (imagem, vídeo, áudio, voz/ptt, sticker, documento). A extensão
// correta é o que faz o express.static servir o Content-Type certo — sem ele
// o <img>/<video>/<audio> do clone não renderiza o preview.
const MIME_EXT = {
  'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/png': '.png',
  'image/webp': '.webp', 'image/gif': '.gif', 'image/bmp': '.bmp',
  'image/heic': '.heic',
  'video/mp4': '.mp4', 'video/3gpp': '.3gp', 'video/quicktime': '.mov',
  'video/webm': '.webm', 'video/x-matroska': '.mkv',
  'audio/ogg': '.ogg', 'audio/mpeg': '.mp3', 'audio/mp4': '.m4a',
  'audio/aac': '.aac', 'audio/amr': '.amr', 'audio/wav': '.wav',
  'audio/x-wav': '.wav', 'audio/webm': '.weba',
  'application/pdf': '.pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
  'application/msword': '.doc',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
  'application/vnd.ms-excel': '.xls',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
  'application/vnd.ms-powerpoint': '.ppt',
  'text/plain': '.txt', 'text/csv': '.csv', 'application/zip': '.zip',
};

/**
 * Resolve a extensão a partir do mimetype, tolerando parâmetros
 * (ex.: "audio/ogg; codecs=opus") e mimetypes desconhecidos (-> .bin).
 */
function extFromMime(mimetype) {
  if (!mimetype) return '.bin';
  const base = String(mimetype).split(';')[0].trim().toLowerCase();
  return MIME_EXT[base] || '.bin';
}

/**
 * Verificar se mensagem tem midia
 */
function hasMedia(message) {
  return message && message.hasMedia === true;
}

/**
 * Verificar se e um tipo de arquivo aceito para CV
 */
function isAcceptedCVType(mimetype) {
  return ACCEPTED_CV_TYPES.hasOwnProperty(mimetype);
}

/**
 * Verificar se e PDF
 */
function isPDF(mimetype) {
  return mimetype === 'application/pdf';
}

/**
 * Download e salvar arquivo de midia do WhatsApp
 * @param {object} message - Mensagem do WhatsApp com hasMedia=true
 * @param {string} phone - Numero do telefone (para nomear arquivo)
 * @returns {object} - { success, filePath, filename, mimetype, size }
 */
async function downloadAndSaveMedia(message, phone) {
  try {
    if (!message.hasMedia) {
      return { success: false, error: 'Mensagem nao contem midia' };
    }

    // Baixar midia
    const media = await message.downloadMedia();

    if (!media) {
      return { success: false, error: 'Falha ao baixar midia' };
    }

    const mimetype = media.mimetype || 'application/octet-stream';
    const extension = extFromMime(mimetype);

    // Gerar nome de arquivo unico
    const timestamp = Date.now();
    const cleanPhone = phone.replace(/\D/g, '');
    const filename = `${cleanPhone}_${timestamp}${extension}`;
    const filePath = path.join(MEDIA_DIR, filename);

    // Converter base64 para buffer e salvar
    const buffer = Buffer.from(media.data, 'base64');
    fs.writeFileSync(filePath, buffer);

    const stats = fs.statSync(filePath);

    console.log(`[MEDIA] Arquivo salvo: ${filename} (${Math.round(stats.size / 1024)}KB)`);

    return {
      success: true,
      filePath: filePath,
      filename: filename,
      mimetype: mimetype,
      size: stats.size,
      extension: extension
    };
  } catch (error) {
    console.error('[MEDIA] Erro ao baixar/salvar:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Processar arquivo de CV (PDF, DOCX, etc)
 * Retorna info do arquivo e texto extraido se possivel
 */
async function processCVFile(message, phone) {
  const mediaResult = await downloadAndSaveMedia(message, phone);

  if (!mediaResult.success) {
    return mediaResult;
  }

  // Para PDFs, tentar extrair texto basico (se pdf-parse estiver disponivel)
  let extractedText = null;
  if (mediaResult.mimetype === 'application/pdf') {
    try {
      // Tentar usar pdf-parse se disponivel
      const pdfParse = require('pdf-parse');
      const dataBuffer = fs.readFileSync(mediaResult.filePath);
      const pdfData = await pdfParse(dataBuffer);
      extractedText = pdfData.text;
      console.log(`[MEDIA] Texto extraido do PDF: ${extractedText.length} caracteres`);
    } catch (e) {
      // pdf-parse nao instalado ou erro - continuar sem extracao
      console.log('[MEDIA] Extracao de texto PDF nao disponivel:', e.message);
    }
  }

  return {
    ...mediaResult,
    extractedText: extractedText,
    isCV: true
  };
}

/**
 * Extrai o texto de um PDF (OCR automático de documentos recebidos).
 *
 * Defensivo de propósito: pdf-parse v1 exporta a função direto; v2 pode
 * expor { pdf } ou { default }. Qualquer falha (lib ausente, PDF imagem-only,
 * API diferente) devolve null — o documento ainda funciona como anexo, só
 * sem o texto extraído. Saída limitada a maxChars para o payload da bridge
 * ficar enxuto.
 */
async function extractPdfText(filePath, maxChars = 8000) {
  try {
    let mod;
    try {
      mod = require('pdf-parse');
    } catch (e) {
      console.log('[OCR] pdf-parse indisponivel:', e.message);
      return null;
    }
    const fn =
      typeof mod === 'function' ? mod
      : (mod && typeof mod.pdf === 'function') ? mod.pdf
      : (mod && typeof mod.default === 'function') ? mod.default
      : null;
    if (!fn) {
      console.log('[OCR] API do pdf-parse nao reconhecida');
      return null;
    }
    const dataBuffer = fs.readFileSync(filePath);
    const data = await fn(dataBuffer);
    const text = data && data.text ? String(data.text).trim() : '';
    if (!text) return null;
    console.log(`[OCR] PDF: ${text.length} caracteres extraidos`);
    return text.length > maxChars ? text.slice(0, maxChars) : text;
  } catch (e) {
    console.log('[OCR] extracao de PDF falhou:', e.message);
    return null;
  }
}

/**
 * Obter caminho do diretorio de midia
 */
function getMediaDir() {
  return MEDIA_DIR;
}

/**
 * Listar arquivos de um telefone especifico
 */
function listFilesForPhone(phone) {
  const cleanPhone = phone.replace(/\D/g, '');
  const files = fs.readdirSync(MEDIA_DIR);
  return files.filter(f => f.startsWith(cleanPhone));
}

/**
 * Deletar arquivos antigos (mais de X dias)
 */
function cleanOldFiles(daysOld = 30) {
  const cutoffDate = Date.now() - (daysOld * 24 * 60 * 60 * 1000);
  const files = fs.readdirSync(MEDIA_DIR);
  let deleted = 0;

  for (const file of files) {
    const filePath = path.join(MEDIA_DIR, file);
    const stats = fs.statSync(filePath);

    if (stats.mtime.getTime() < cutoffDate) {
      fs.unlinkSync(filePath);
      deleted++;
    }
  }

  if (deleted > 0) {
    console.log(`[MEDIA] ${deleted} arquivos antigos removidos`);
  }

  return deleted;
}

module.exports = {
  MEDIA_DIR,
  ACCEPTED_CV_TYPES,
  ACCEPTED_IMAGE_TYPES,
  MIME_EXT,
  extFromMime,
  hasMedia,
  isAcceptedCVType,
  isPDF,
  downloadAndSaveMedia,
  processCVFile,
  extractPdfText,
  getMediaDir,
  listFilesForPhone,
  cleanOldFiles
};
