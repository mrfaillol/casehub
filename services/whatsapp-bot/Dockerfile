# WhatsApp bot (lite) — CaseHub alpha
# whatsapp-web.js usa Puppeteer → precisa de Chromium + libs no container.
#
# Decisões de imagem:
#   - node:20-bookworm-slim fornece Chromium do sistema via apt (pacote `chromium`),
#     em /usr/bin/chromium. Não usamos a imagem Alpine: o Chromium do Alpine
#     (musl) costuma quebrar com whatsapp-web.js / Puppeteer.
#   - `git` é OBRIGATÓRIO: a dependência whatsapp-web.js é um fork GitHub
#     (timothydillan/whatsapp-web.js#fix/...) — npm precisa de git para resolvê-la.
#
# shm: Puppeteer/Chromium usam /dev/shm. O default do Docker (64MB) é pequeno
#      e causa crashes do renderer. Mitigado por dois caminhos complementares:
#        1. flag `--disable-dev-shm-usage` no whatsapp-client.js (usa /tmp);
#        2. o serviço compose deve setar `shm_size: 1gb`.
#      Manter os dois — a flag sozinha basta para o alpha, o shm_size é o cinto.
FROM node:20-bookworm-slim

# Chromium + dependências do Puppeteer
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        ca-certificates \
        git \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdrm2 \
        libgbm1 \
        libnspr4 \
        libnss3 \
        libx11-6 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxrandr2 \
        libxkbcommon0 \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Puppeteer usa o Chromium do sistema (não baixa o próprio).
# PUPPETEER_EXECUTABLE_PATH é lido por whatsapp-client.js -> puppeteer.executablePath.
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV NODE_ENV=production

WORKDIR /app

# Instala dependências primeiro (cache de layer).
# package-lock.json* é opcional — se não existir, npm resolve do package.json.
COPY package.json package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund

# Código do bot
COPY . .

# Sessão whatsapp-web.js persiste aqui (montar volume para sobreviver a restart).
RUN mkdir -p /app/.wwebjs_auth

EXPOSE 3001

# Healthcheck — /health responde 200 quando o bot está saudável.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3001/health > /dev/null 2>&1 || exit 1

# server-lite: subconjunto alpha (sem Moskit/Stripe/callhippo legado).
CMD ["node", "server-lite.js"]
