/**
 * Generate WhatsApp Pairing Code
 * Número: +1 (940) 618-3140
 */

const puppeteer = require('puppeteer');

const PHONE_NUMBER = process.argv[2] || '9406183140';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function generatePairingCode() {
  console.log('[PAIRING] Iniciando para número: +1', PHONE_NUMBER);
  
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: false,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--no-first-run',
        '--no-zygote',
        '--disable-gpu',
        '--window-size=1280,800'
      ]
    });
    
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800 });
    
    console.log('[PAIRING] Navegando para WhatsApp Web...');
    await page.goto('https://web.whatsapp.com/', { 
      waitUntil: 'networkidle2',
      timeout: 60000 
    });
    
    console.log('[PAIRING] Aguardando 10s...');
    await sleep(10000);
    
    // PASSO 1: Clicar em "Log in with phone number"
    console.log('[PAIRING] Clicando em "Log in with phone number"...');
    
    await page.evaluate(() => {
      const allElements = document.querySelectorAll('*');
      for (const el of allElements) {
        if (el.textContent && el.textContent.trim() === 'Log in with phone number') {
          el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
          return true;
        }
      }
      return false;
    });
    
    await sleep(5000);
    console.log('[PAIRING] Tela de telefone alcançada!');
    
    // PASSO 2: Clicar no dropdown de país
    console.log('[PAIRING] Abrindo dropdown de país...');
    await page.mouse.click(640, 275);
    await sleep(2000);
    
    // PASSO 3: Digitar para filtrar e selecionar USA
    console.log('[PAIRING] Selecionando United States...');
    await page.keyboard.type('united states');
    await sleep(1500);
    
    // Navega até United States e seleciona
    await page.keyboard.press('ArrowDown');
    await sleep(300);
    await page.keyboard.press('ArrowDown');
    await sleep(300);
    await page.keyboard.press('Enter');
    await sleep(2000);
    
    await page.screenshot({ path: '/tmp/wa-usa-selected.png' });
    
    // PASSO 4: Verificar o input atual
    let inputValue = await page.evaluate(() => {
      const input = document.querySelector('input[type="text"]');
      return input ? input.value : null;
    });
    console.log('[PAIRING] Valor atual no input:', inputValue);
    
    // PASSO 5: Clicar no input e posicionar cursor no final
    console.log('[PAIRING] Clicando no input...');
    const input = await page.$('input[type="text"]');
    if (input) {
      // Clica no input
      await input.click();
      await sleep(500);
      
      // Move o cursor para o final (End key)
      await page.keyboard.press('End');
      await sleep(300);
      
      // Adiciona um espaço se necessário
      if (inputValue && !inputValue.endsWith(' ')) {
        await page.keyboard.type(' ');
      }
      
      // Digita o número APÓS o +1
      console.log('[PAIRING] Adicionando número ao final...');
      await page.keyboard.type(PHONE_NUMBER, { delay: 80 });
      
      await sleep(1000);
    }
    
    // Verifica o valor após digitar
    inputValue = await page.evaluate(() => {
      const input = document.querySelector('input[type="text"]');
      return input ? input.value : null;
    });
    console.log('[PAIRING] Valor após digitar:', inputValue);
    
    await page.screenshot({ path: '/tmp/wa-number-entered.png' });
    
    // Verifica se o país ainda é USA
    const countryText = await page.evaluate(() => {
      const elements = document.querySelectorAll('span, div');
      for (const el of elements) {
        if (el.textContent && (el.textContent.includes('United States') || el.textContent.includes('Sri Lanka') || el.textContent.includes('Brazil'))) {
          return el.textContent;
        }
      }
      return null;
    });
    console.log('[PAIRING] País atual:', countryText);
    
    // PASSO 6: Clicar em Next
    console.log('[PAIRING] Clicando em Next...');
    
    await page.evaluate(() => {
      const buttons = document.querySelectorAll('button');
      for (const btn of buttons) {
        if (btn.textContent && btn.textContent.trim() === 'Next') {
          btn.click();
          return true;
        }
      }
      return false;
    });
    
    // PASSO 7: Aguardar código de pareamento
    console.log('[PAIRING] Aguardando código de pareamento (35s)...');
    await sleep(35000);
    
    await page.screenshot({ path: '/tmp/wa-final-code.png' });
    
    // Extrai o código
    const pageText = await page.evaluate(() => document.body.innerText);
    
    console.log('[PAIRING] ============================================');
    console.log('[PAIRING] CONTEÚDO DA PÁGINA:');
    console.log(pageText);
    console.log('[PAIRING] ============================================');
    
    // Procura padrões de código de pareamento
    // O código geralmente é 8 caracteres alfanuméricos separados por hífen ou espaço
    const lines = pageText.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      // Verifica se a linha parece um código (8 caracteres, alfanuméricos)
      if (/^[A-Z0-9]{4}[- ]?[A-Z0-9]{4}$/i.test(trimmed)) {
        console.log('[PAIRING] >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>');
        console.log('[PAIRING] CÓDIGO DE PAREAMENTO: ' + trimmed);
        console.log('[PAIRING] <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<');
      }
    }
    
    await sleep(5000);
    
  } catch (error) {
    console.error('[PAIRING] Erro:', error.message);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

generatePairingCode();
