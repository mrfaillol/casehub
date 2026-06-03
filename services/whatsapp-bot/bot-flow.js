/**
 * Bot Flow - Sistema de perguntas sequenciais (sem IA)
 * CaseHub
 * v8.4 - Smart Name Detection EXPANDIDO MASSIVAMENTE
 */

const { detectLanguage, getMessages } = require('./languages');

const STATES = {
  NEW: 'new',
  ASKED_NAME: 'asked_name',
  ASKED_INTEREST: 'asked_interest',
  ASKED_EMAIL: 'asked_email',
  ASKED_CONSULTATION_TYPE: 'asked_consultation_type',
  AWAITING_PAYMENT: 'awaiting_payment',
  ASKED_SCHEDULING: 'asked_scheduling',
  TRANSFERRED: 'transferred'
};

const CONSULTATION_TYPES = {
  '1': 'free',
  '2': 'paid'
};

// ===== SMART NAME DETECTION v8.4 - LISTA MASSIVAMENTE EXPANDIDA =====

// Verbos conjugados comuns (primeira pessoa, terceira pessoa, infinitivo)
const VERBOS_PT = [
  // Ser/Estar/Ter/Haver
  'sou', 'estou', 'tenho', 'havia', 'houve', 'era', 'estava', 'tinha',
  'somos', 'estamos', 'temos', 'são', 'estão', 'têm',
  'ser', 'estar', 'ter', 'haver',
  // Verbos de ação comuns
  'quero', 'queria', 'quer', 'querem', 'querer',
  'preciso', 'precisava', 'precisa', 'precisam', 'precisar',
  'gostaria', 'gosto', 'gostei', 'gostar',
  'posso', 'podia', 'pode', 'podem', 'poder',
  'sei', 'sabia', 'sabe', 'sabem', 'saber',
  'vou', 'vamos', 'vai', 'vão', 'ir',
  'vim', 'veio', 'viemos', 'vieram', 'vir',
  'fui', 'foi', 'fomos', 'foram',
  'fiz', 'fez', 'fizemos', 'fizeram', 'fazer',
  'disse', 'diz', 'dizem', 'dizer',
  'vi', 'viu', 'viram', 'ver',
  'li', 'leu', 'leram', 'ler',
  'ouvi', 'ouviu', 'ouviram', 'ouvir',
  'achei', 'acho', 'acha', 'acham', 'achar',
  'penso', 'pensava', 'pensa', 'pensam', 'pensar',
  'trabalho', 'trabalha', 'trabalham', 'trabalhar', 'trabalhei', 'trabalhou',
  'moro', 'mora', 'moram', 'morar', 'morei', 'morou',
  'vivo', 'vive', 'vivem', 'viver', 'vivi', 'viveu',
  'cheguei', 'chegou', 'chegaram', 'chegar',
  'voltei', 'voltou', 'voltaram', 'voltar',
  'saí', 'saiu', 'saíram', 'sair',
  'entrei', 'entrou', 'entraram', 'entrar',
  'fiquei', 'ficou', 'ficaram', 'ficar',
  'ligo', 'liga', 'ligam', 'ligar', 'liguei', 'ligou',
  'mando', 'manda', 'mandam', 'mandar', 'mandei', 'mandou',
  'envio', 'envia', 'enviam', 'enviar', 'enviei', 'enviou',
  'pago', 'paga', 'pagam', 'pagar', 'paguei', 'pagou',
  'compro', 'compra', 'compram', 'comprar', 'comprei', 'comprou',
  'vendo', 'vende', 'vendem', 'vender', 'vendi', 'vendeu',
  'ajudo', 'ajuda', 'ajudam', 'ajudar', 'ajudei', 'ajudou',
  'peço', 'pede', 'pedem', 'pedir', 'pedi', 'pediu',
  'espero', 'espera', 'esperam', 'esperar', 'esperei', 'esperou',
  'aguardo', 'aguarda', 'aguardam', 'aguardar', 'aguardei', 'aguardou',
  'entendo', 'entende', 'entendem', 'entender', 'entendi', 'entendeu',
  'conheço', 'conhece', 'conhecem', 'conhecer', 'conheci', 'conheceu',
  'consigo', 'consegue', 'conseguem', 'conseguir', 'consegui', 'conseguiu',
  'deixo', 'deixa', 'deixam', 'deixar', 'deixei', 'deixou',
  'passo', 'passa', 'passam', 'passar', 'passei', 'passou',
  'busco', 'busca', 'buscam', 'buscar', 'busquei', 'buscou',
  'procuro', 'procura', 'procuram', 'procurar', 'procurei', 'procurou',
  'encontro', 'encontra', 'encontram', 'encontrar', 'encontrei', 'encontrou',
  'perdi', 'perdeu', 'perderam', 'perder',
  'casei', 'casou', 'casaram', 'casar',
  'separei', 'separou', 'separaram', 'separar',
  'divorciei', 'divorciou', 'divorciaram', 'divorciar',
  'nasci', 'nasceu', 'nasceram', 'nascer',
  'morri', 'morreu', 'morreram', 'morrer',
  'sofri', 'sofreu', 'sofreram', 'sofrer',
  'recebi', 'recebeu', 'receberam', 'receber',
  'peguei', 'pegou', 'pegaram', 'pegar',
  'tirei', 'tirou', 'tiraram', 'tirar',
  'coloquei', 'colocou', 'colocaram', 'colocar',
  'comecei', 'começou', 'começaram', 'começar',
  'terminei', 'terminou', 'terminaram', 'terminar',
  'continuo', 'continua', 'continuam', 'continuar', 'continuei', 'continuou',
  'parei', 'parou', 'pararam', 'parar',
  'tentei', 'tentou', 'tentaram', 'tentar',
  'decidi', 'decidiu', 'decidiram', 'decidir',
  'escolhi', 'escolheu', 'escolheram', 'escolher',
  'prefiro', 'prefere', 'preferem', 'preferir', 'preferi', 'preferiu',
  'aceito', 'aceita', 'aceitam', 'aceitar', 'aceitei', 'aceitou',
  'nego', 'nega', 'negam', 'negar', 'neguei', 'negou',
  'recuso', 'recusa', 'recusam', 'recusar', 'recusei', 'recusou',
  // Verbos de imigração
  'imigrei', 'imigrou', 'imigraram', 'imigrar',
  'emigrei', 'emigrou', 'emigraram', 'emigrar',
  'deportaram', 'deportar', 'deportado',
  'apliquei', 'aplicou', 'aplicaram', 'aplicar',
  'solicitei', 'solicitou', 'solicitaram', 'solicitar',
  'renovei', 'renovou', 'renovaram', 'renovar',
  'expirou', 'expiraram', 'expirar',
  'venceu', 'venceram', 'vencer',
  'aprovaram', 'aprovar', 'aprovado', 'aprovei', 'aprovou',
  'negaram', 'negar', 'negado',
  'agendei', 'agendou', 'agendaram', 'agendar',
  'marquei', 'marcou', 'marcaram', 'marcar',
];

// Verbos em inglês
const VERBOS_EN = [
  'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'have', 'has', 'had', 'having',
  'do', 'does', 'did', 'doing', 'done',
  'will', 'would', 'could', 'should', 'can', 'may', 'might', 'must',
  'want', 'wanted', 'wanting', 'wants',
  'need', 'needed', 'needing', 'needs',
  'like', 'liked', 'liking', 'likes',
  'know', 'knew', 'knowing', 'knows',
  'think', 'thought', 'thinking', 'thinks',
  'go', 'went', 'going', 'goes', 'gone',
  'come', 'came', 'coming', 'comes',
  'get', 'got', 'getting', 'gets',
  'make', 'made', 'making', 'makes',
  'see', 'saw', 'seeing', 'sees', 'seen',
  'look', 'looked', 'looking', 'looks',
  'call', 'called', 'calling', 'calls',
  'live', 'lived', 'living', 'lives',
  'work', 'worked', 'working', 'works',
  'move', 'moved', 'moving', 'moves',
  'stay', 'stayed', 'staying', 'stays',
  'leave', 'left', 'leaving', 'leaves',
  'arrive', 'arrived', 'arriving', 'arrives',
  'return', 'returned', 'returning', 'returns',
  'apply', 'applied', 'applying', 'applies',
  'wait', 'waited', 'waiting', 'waits',
  'help', 'helped', 'helping', 'helps',
  'ask', 'asked', 'asking', 'asks',
  'tell', 'told', 'telling', 'tells',
  'say', 'said', 'saying', 'says',
  'send', 'sent', 'sending', 'sends',
  'receive', 'received', 'receiving', 'receives',
  'pay', 'paid', 'paying', 'pays',
  'buy', 'bought', 'buying', 'buys',
  'sell', 'sold', 'selling', 'sells',
  'try', 'tried', 'trying', 'tries',
  'start', 'started', 'starting', 'starts',
  'stop', 'stopped', 'stopping', 'stops',
  'continue', 'continued', 'continuing', 'continues',
];

// Verbos em espanhol
const VERBOS_ES = [
  'soy', 'estoy', 'tengo', 'era', 'estaba', 'tenía',
  'somos', 'estamos', 'tenemos', 'son', 'están', 'tienen',
  'quiero', 'quería', 'quiere', 'quieren', 'querer',
  'necesito', 'necesitaba', 'necesita', 'necesitan', 'necesitar',
  'puedo', 'podía', 'puede', 'pueden', 'poder',
  'sé', 'sabía', 'sabe', 'saben', 'saber',
  'voy', 'vamos', 'va', 'van', 'ir',
  'vine', 'vino', 'vinimos', 'vinieron', 'venir',
  'fui', 'fue', 'fuimos', 'fueron',
  'hice', 'hizo', 'hicimos', 'hicieron', 'hacer',
  'vivo', 'vive', 'viven', 'vivir', 'viví', 'vivió',
  'trabajo', 'trabaja', 'trabajan', 'trabajar', 'trabajé', 'trabajó',
  'llamo', 'llama', 'llaman', 'llamar', 'llamé', 'llamó',
  'busco', 'busca', 'buscan', 'buscar', 'busqué', 'buscó',
  'espero', 'espera', 'esperan', 'esperar', 'esperé', 'esperó',
  'ayudo', 'ayuda', 'ayudan', 'ayudar', 'ayudé', 'ayudó',
];

// Advérbios e palavras temporais
const ADVERBIOS = [
  // Português
  'já', 'ja', 'ainda', 'agora', 'hoje', 'ontem', 'amanhã', 'amanha',
  'sempre', 'nunca', 'jamais', 'talvez', 'depois', 'antes', 'logo',
  'aqui', 'ali', 'lá', 'la', 'cá', 'ca', 'onde', 'aonde',
  'muito', 'pouco', 'mais', 'menos', 'bem', 'mal', 'assim',
  'também', 'tambem', 'só', 'so', 'apenas', 'quase', 'mesmo',
  'realmente', 'certamente', 'provavelmente', 'possivelmente',
  'infelizmente', 'felizmente', 'obviamente', 'claramente',
  // Inglês
  'already', 'still', 'yet', 'now', 'today', 'yesterday', 'tomorrow',
  'always', 'never', 'sometimes', 'often', 'usually', 'rarely',
  'here', 'there', 'where', 'somewhere', 'anywhere', 'everywhere',
  'very', 'much', 'more', 'less', 'well', 'badly', 'quickly', 'slowly',
  'also', 'too', 'only', 'just', 'almost', 'really', 'certainly',
  'probably', 'possibly', 'maybe', 'perhaps', 'definitely',
  // Espanhol
  'ya', 'todavía', 'todavia', 'ahora', 'hoy', 'ayer', 'mañana', 'manana',
  'siempre', 'nunca', 'jamás', 'jamas', 'quizás', 'quizas', 'después', 'despues',
  'aquí', 'aqui', 'allí', 'alli', 'allá', 'alla', 'donde', 'adonde',
  'muy', 'mucho', 'poco', 'más', 'mas', 'menos', 'bien', 'mal',
  'también', 'tambien', 'solo', 'sólo', 'casi', 'realmente',
];

// Preposições e artigos
const PREPOSICOES_ARTIGOS = [
  // Português
  'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas',
  'de', 'da', 'do', 'das', 'dos', 'dum', 'duma',
  'em', 'na', 'no', 'nas', 'nos', 'num', 'numa',
  'por', 'pela', 'pelo', 'pelas', 'pelos',
  'para', 'pra', 'pro',
  'com', 'sem', 'sob', 'sobre', 'entre', 'até', 'ate',
  'desde', 'durante', 'mediante', 'perante', 'segundo', 'conforme',
  // Inglês
  'the', 'a', 'an',
  'of', 'to', 'in', 'on', 'at', 'by', 'for', 'with', 'without',
  'from', 'into', 'onto', 'upon', 'about', 'through', 'during',
  'before', 'after', 'above', 'below', 'between', 'among', 'under', 'over',
  // Espanhol
  'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
  'de', 'del', 'al',
  'en', 'por', 'para', 'con', 'sin', 'sobre', 'entre', 'hasta',
  'desde', 'durante', 'mediante', 'según', 'segun',
];

// Conjunções
const CONJUNCOES = [
  // Português
  'e', 'ou', 'mas', 'porém', 'porem', 'contudo', 'todavia', 'entretanto',
  'porque', 'pois', 'que', 'se', 'quando', 'como', 'enquanto',
  'embora', 'apesar', 'caso', 'portanto', 'logo', 'então', 'entao',
  // Inglês
  'and', 'or', 'but', 'however', 'therefore', 'because', 'since',
  'if', 'when', 'while', 'although', 'though', 'unless', 'until',
  'so', 'yet', 'nor', 'either', 'neither', 'both', 'whether',
  // Espanhol
  'y', 'o', 'pero', 'sino', 'porque', 'pues', 'que', 'si', 'cuando',
  'como', 'mientras', 'aunque', 'sin embargo', 'por lo tanto',
];

// Pronomes
const PRONOMES = [
  // Português
  'eu', 'tu', 'você', 'voce', 'vocês', 'voces', 'ele', 'ela', 'eles', 'elas',
  'nós', 'nos', 'vós', 'vos', 'a gente',
  'me', 'te', 'se', 'lhe', 'lhes',
  'meu', 'minha', 'meus', 'minhas', 'teu', 'tua', 'teus', 'tuas',
  'seu', 'sua', 'seus', 'suas', 'nosso', 'nossa', 'nossos', 'nossas',
  'este', 'esta', 'estes', 'estas', 'esse', 'essa', 'esses', 'essas',
  'aquele', 'aquela', 'aqueles', 'aquelas', 'isto', 'isso', 'aquilo',
  'quem', 'qual', 'quais', 'quanto', 'quanta', 'quantos', 'quantas',
  'algo', 'alguém', 'alguem', 'ninguém', 'ninguem', 'nada', 'tudo',
  'algum', 'alguma', 'alguns', 'algumas', 'nenhum', 'nenhuma',
  'outro', 'outra', 'outros', 'outras', 'mesmo', 'mesma', 'mesmos', 'mesmas',
  // Inglês
  'i', 'you', 'he', 'she', 'it', 'we', 'they',
  'me', 'him', 'her', 'us', 'them',
  'my', 'your', 'his', 'her', 'its', 'our', 'their',
  'mine', 'yours', 'hers', 'ours', 'theirs',
  'this', 'that', 'these', 'those',
  'who', 'whom', 'whose', 'which', 'what',
  'someone', 'somebody', 'anyone', 'anybody', 'everyone', 'everybody',
  'no one', 'nobody', 'something', 'anything', 'everything', 'nothing',
  'myself', 'yourself', 'himself', 'herself', 'itself', 'ourselves', 'themselves',
  // Espanhol
  'yo', 'tú', 'tu', 'usted', 'él', 'el', 'ella', 'nosotros', 'nosotras',
  'vosotros', 'vosotras', 'ustedes', 'ellos', 'ellas',
  'mi', 'mis', 'tu', 'tus', 'su', 'sus', 'nuestro', 'nuestra', 'nuestros', 'nuestras',
  'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
  'aquel', 'aquella', 'aquellos', 'aquellas', 'esto', 'eso', 'aquello',
  'quien', 'quién', 'cual', 'cuál', 'cuales', 'cuáles',
  'alguien', 'nadie', 'algo', 'nada', 'todo', 'todos', 'todas',
];

// Saudações e despedidas
const SAUDACOES = [
  // Português
  'oi', 'olá', 'ola', 'alô', 'alo', 'bom dia', 'boa tarde', 'boa noite',
  'opa', 'eai', 'e ai', 'e aí', 'fala', 'salve', 'beleza', 'blz',
  'tudo bem', 'tudo bom', 'tudo certo', 'como vai', 'como está',
  'obrigado', 'obrigada', 'valeu', 'vlw', 'brigado', 'brigada',
  'tchau', 'adeus', 'até logo', 'ate logo', 'até mais', 'ate mais',
  'abraço', 'abraços', 'beijo', 'beijos', 'bjo', 'bjs',
  // Inglês
  'hi', 'hello', 'hey', 'howdy', 'greetings',
  'good morning', 'good afternoon', 'good evening', 'good night',
  'whats up', "what's up", 'sup', 'yo',
  'how are you', "how's it going", 'how do you do',
  'thanks', 'thank you', 'thx', 'ty',
  'bye', 'goodbye', 'see you', 'later', 'take care',
  // Espanhol
  'hola', 'buenos días', 'buenos dias', 'buenas tardes', 'buenas noches',
  'qué tal', 'que tal', 'cómo estás', 'como estas', 'cómo está', 'como esta',
  'gracias', 'muchas gracias',
  'adiós', 'adios', 'hasta luego', 'hasta pronto', 'chao', 'chau',
];

// Expressões comuns (frases que pessoas digitam que não são nomes)
const EXPRESSOES_COMUNS = [
  // Interesse/Intenção
  'tenho interesse', 'tenho interese', 'interesse', 'interessado', 'interessada',
  'quero saber', 'quero informações', 'quero informacoes', 'queria saber',
  'queria mais', 'queria informações', 'queria informacoes',
  'gostaria de saber', 'gostaria de', 'gostaria',
  'preciso de ajuda', 'preciso ajuda', 'preciso de informações', 'preciso de informacoes',
  'me ajudem', 'me ajuda', 'podem me ajudar', 'pode me ajudar',
  'vocês me ajudam', 'vcs me ajudam', 'voces me ajudam',
  'quero ajuda', 'preciso de você', 'preciso de voce',
  
  // Perguntas
  'como funciona', 'como faço', 'como faco', 'como posso', 'como que',
  'quanto custa', 'qual o valor', 'qual valor', 'qual o preço', 'qual preco',
  'quanto tempo', 'quanto demora', 'quando posso',
  'onde fica', 'onde é', 'onde e', 'onde vocês', 'onde voces',
  'o que é', 'o que e', 'o que preciso', 'o que fazer',
  'por que', 'por quê', 'porque', 'pra que', 'para que',
  
  // Sobre estar/viver nos EUA
  'já estive', 'ja estive', 'já fui', 'ja fui', 'já morei', 'ja morei',
  'estive em', 'fui para', 'morei em', 'moro em', 'moro nos',
  'estou nos eua', 'estou nos estados unidos', 'estou em',
  'vivo nos eua', 'vivo nos estados unidos', 'vivo em',
  'preciso retornar', 'quero retornar', 'quero voltar', 'preciso voltar',
  'quero ir', 'preciso ir', 'vou para', 'vou pros',
  'vim dos eua', 'vim dos estados unidos', 'voltei dos',
  'meu visto', 'minha situação', 'minha situacao',
  
  // Adiamento/Desinteresse
  'depois ligo', 'depois eu ligo', 'ligo depois', 'te ligo depois',
  'depois falo', 'depois a gente fala', 'depois conversamos',
  'não agora', 'nao agora', 'agora não', 'agora nao', 'mais tarde',
  'outra hora', 'outro dia', 'sem tempo', 'estou ocupado', 'estou ocupada',
  'não posso', 'nao posso', 'não dá', 'nao da', 'não consigo', 'nao consigo',
  'vou pensar', 'deixa eu ver', 'deixa eu pensar',
  'ainda não', 'ainda nao', 'não sei', 'nao sei',
  
  // Afirmações/Negações
  'sim', 'não', 'nao', 'ok', 'okay', 'certo', 'claro', 'com certeza',
  'pode ser', 'tá bom', 'ta bom', 'tá bem', 'ta bem', 'beleza',
  'entendi', 'entendido', 'compreendi', 'compreendido',
  'concordo', 'aceito', 'confirmo', 'confirmado',
  'não sei', 'nao sei', 'não entendi', 'nao entendi',
  'não quero', 'nao quero', 'não preciso', 'nao preciso',
  
  // Pedidos/Solicitações
  'por favor', 'por gentileza', 'me ajude', 'me ajuda',
  'pode me ajudar', 'podem me ajudar', 'preciso de ajuda',
  'gostaria de agendar', 'quero agendar', 'preciso agendar',
  'gostaria de marcar', 'quero marcar', 'preciso marcar',
  'me liga', 'me ligue', 'me chama', 'me chame',
  'entra em contato', 'entre em contato', 'entrar em contato',
  
  // Sobre vistos e imigração
  'green card', 'greencard', 'visto', 'visa', 'cidadania', 'citizenship',
  'ciudadanía', 'ciudadania', 'naturalização', 'naturalizacao',
  'eb1', 'eb2', 'eb3', 'eb4', 'eb5', 'eb-1', 'eb-2', 'eb-3', 'eb-4', 'eb-5',
  'h1b', 'h1-b', 'h-1b', 'l1', 'l-1', 'o1', 'o-1', 'b1', 'b2', 'b1/b2',
  'k1', 'k-1', 'f1', 'f-1', 'j1', 'j-1', 'tn', 'perm', 'i-140', 'i140',
  'i-485', 'i485', 'i-130', 'i130', 'i-20', 'i20', 'ds-160', 'ds160',
  'esta', 'ead', 'ssn', 'social security',
  'green card casamento', 'marriage green card', 'casamento',
  'asilo', 'asylum', 'refugio', 'refúgio', 'refugee',
  'deportação', 'deportacao', 'deportacion', 'deportation', 'deportado',
  'imigração', 'imigracao', 'immigration', 'inmigración', 'inmigracion',
  'trabalho', 'work', 'trabajo', 'work permit', 'permiso de trabajo',
  'visto de trabalho', 'visto de turismo', 'visto de estudante',
  'work visa', 'tourist visa', 'student visa',
  'extensão', 'extensao', 'extension', 'renovação', 'renovacao', 'renewal',
  'entrevista', 'interview', 'consulado', 'consulate', 'embaixada', 'embassy',
  
  // Profissões (quando usadas como resposta, não como nome)
  'advogado', 'advogada', 'lawyer', 'attorney', 'abogado', 'abogada',
  'médico', 'medico', 'médica', 'medica', 'doctor', 'physician',
  'engenheiro', 'engenheira', 'engineer', 'ingeniero', 'ingeniera',
  'empresário', 'empresaria', 'empresario', 'entrepreneur', 'business owner',
  'programador', 'programadora', 'programmer', 'developer', 'desarrollador',
  'enfermeiro', 'enfermeira', 'nurse', 'enfermero', 'enfermera',
  'professor', 'professora', 'teacher', 'profesor', 'profesora',
  'contador', 'contadora', 'accountant',
  
  // Números e opções
  '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
  'um', 'dois', 'tres', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez',
  'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
  'primeiro', 'primeira', 'segundo', 'segunda', 'terceiro', 'terceira',
  'first', 'second', 'third', 'fourth', 'fifth',
  'outros', 'outro', 'outra', 'other', 'others', 'otra', 'otro', 'otras', 'otros',
  'opção', 'opcao', 'option', 'opción', 'opcion',
  
  // Palavras soltas comuns
  'informação', 'informacao', 'information', 'información', 'informacion',
  'informações', 'informacoes', 'mais informações', 'more information',
  'consulta', 'consultation', 'consulta gratuita', 'free consultation',
  'agendar', 'schedule', 'marcar', 'booking', 'appointment',
  'preço', 'preco', 'price', 'precio', 'valor', 'cost', 'costo', 'custo',
  'urgente', 'urgent', 'emergência', 'emergencia', 'emergency',
  'dúvida', 'duvida', 'question', 'pregunta', 'doubt', 'questão', 'questao',
  'processo', 'process', 'proceso', 'caso', 'case',
  'documento', 'documentos', 'document', 'documents', 'papeis', 'papéis',
  'formulário', 'formulario', 'form', 'formulários', 'formularios', 'forms',
  
  // Emojis e caracteres
  '👋', '🙋', '✋', '🤚', '👍', '😊', '🙂', '😀', '❤️', '🙏', '👏',
  '!!!', '???', '...', '!!!???',
];

// Combinar tudo em NOT_A_NAME
const NOT_A_NAME = [
  ...VERBOS_PT,
  ...VERBOS_EN,
  ...VERBOS_ES,
  ...ADVERBIOS,
  ...PREPOSICOES_ARTIGOS,
  ...CONJUNCOES,
  ...PRONOMES,
  ...SAUDACOES,
  ...EXPRESSOES_COMUNS
];

// Padrões regex para detectar frases (ainda mais abrangentes)
const NOT_A_NAME_PATTERNS = [
  // Começa com verbo conjugado
  /^(tenho|quero|preciso|gostaria|posso|sei|vou|vim|fui|estou|sou|moro|trabalho|busco|procuro)/i,
  /^(have|want|need|would|can|know|am|is|was|live|work|looking)/i,
  /^(tengo|quiero|necesito|puedo|sé|voy|estoy|soy|vivo|trabajo|busco)/i,
  
  // Começa com advérbio temporal
  /^(já|ja|ainda|agora|hoje|ontem|depois|antes|nunca|sempre)/i,
  /^(already|still|now|today|yesterday|after|before|never|always)/i,
  /^(ya|todavía|todavia|ahora|hoy|ayer|después|despues|nunca|siempre)/i,
  
  // Frases comuns
  /^(oi|olá|ola|hi|hello|hey|hola|bom dia|boa tarde|boa noite|buenos|good)/i,
  /^(me\s+ajud|podem\s+me|pode\s+me|can\s+you|could\s+you)/i,
  /^(como\s+(funciona|faço|faco|posso)|how\s+(does|do|can|could))/i,
  /^(quanto\s+(custa|tempo|demora)|how\s+(much|long))/i,
  /^(por\s+favor|please|por\s+gentileza)/i,
  
  // Sobre localização/situação
  /^(estou|estive|moro|morei|vivo|vivi|fui|vim)\s+(em|nos|na|no|para|de|dos)/i,
  /^(i\s+(live|lived|am|was|went|came))\s+(in|to|from|at)/i,
  
  // Números com texto
  /^\d+\s*(outros?|other|opç|opc)/i,
  /^(opç|opc|option)\s*\d/i,
  
  // Respostas curtas
  /^(sim|não|nao|ok|okay|yes|no|sí|si|claro|certo|beleza)$/i,
  /^(obrigad|thanks|gracias|valeu|vlw)/i,
  
  // Interesses diretos
  /^(green\s*card|visto|visa|cidadania|citizenship|asilo|asylum)/i,
  /^(trabalh|work|morar|live|investir|invest|reunir|family)/i,
  
  // Frases de adiamento
  /^(depois|later|más tarde|mais tarde|outra hora|outro dia)/i,
  /^(não\s+agora|nao\s+agora|not\s+now|ahora\s+no)/i,
  /^(vou\s+pensar|let\s+me\s+think|deixa\s+eu)/i,
];

/**
 * Verificar se uma string é um nome válido
 */
function isValidName(str) {
  if (!str || typeof str !== 'string') return false;

  const cleaned = str.trim().toLowerCase();
  const original = str.trim();

  // Muito curto ou muito longo
  if (cleaned.length < 2 || cleaned.length > 50) return false;

  // Está na lista de não-nomes (verificação exata)
  if (NOT_A_NAME.includes(cleaned)) return false;

  // Verifica padrões de frases (regex)
  for (const pattern of NOT_A_NAME_PATTERNS) {
    if (pattern.test(cleaned)) {
      return false;
    }
  }

  // Começa com palavra da lista NOT_A_NAME
  const firstWord = cleaned.split(/\s+/)[0];
  if (NOT_A_NAME.includes(firstWord)) {
    // Se a primeira palavra é verbo, advérbio, etc., não é nome
    if (VERBOS_PT.includes(firstWord) || VERBOS_EN.includes(firstWord) || VERBOS_ES.includes(firstWord)) return false;
    if (ADVERBIOS.includes(firstWord)) return false;
    if (CONJUNCOES.includes(firstWord)) return false;
    if (PRONOMES.includes(firstWord)) return false;
    if (SAUDACOES.includes(firstWord) && cleaned.split(/\s+/).length > 2) return false;
  }

  // Contém números (nomes não têm números)
  if (/\d/.test(cleaned)) return false;

  // Muitas palavras (provavelmente é uma frase)
  const words = cleaned.split(/\s+/).filter(w => w.length > 0);
  if (words.length > 4) return false;

  // Contém pontuação de frase (vírgula, ponto de interrogação, exclamação múltipla)
  if (/[,?]/.test(cleaned)) return false;
  if (/!{2,}/.test(cleaned)) return false;
  if (/\.{2,}/.test(cleaned)) return false;

  // Contém caracteres suspeitos
  if (/[@#$%^&*()+=\[\]{}|\\<>\/]/.test(cleaned)) return false;

  // Contém palavras funcionais no meio (indica frase)
  const funcWords = ['que', 'como', 'para', 'por', 'com', 'sem', 'mais', 'muito', 'bem', 'mal'];
  for (let i = 1; i < words.length; i++) {
    if (funcWords.includes(words[i])) return false;
  }

  return true;
}

/**
 * Extrair nome real de uma mensagem
 */
function extractRealName(msg, lang = 'en') {
  if (!msg) return null;

  const text = msg.trim();

  // Padrões para extrair nome
  const patterns = [
    // PT
    /(?:meu nome [eé]|me chamo|sou o|sou a|pode me chamar de|eu sou)\s+([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)?)/i,
    // EN
    /(?:my name is|i am|i'm|call me|you can call me)\s+([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)?)/i,
    // ES
    /(?:mi nombre es|me llamo|soy|me pueden llamar)\s+([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)?)/i
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      const extracted = match[1].trim();
      if (isValidName(extracted)) {
        return formatName(extracted);
      }
    }
  }

  return null;
}

/**
 * Formatar nome (capitalizar)
 */
function formatName(name) {
  if (!name) return name;
  return name
    .split(' ')
    .filter(word => word.length > 0)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Verificar se mensagem deve ser ignorada
 */
function shouldIgnoreMessage(message) {
  if (!message) return true;
  const msg = message.trim();
  if (msg.length === 0) return true;
  return false;
}

/**
 * Extrair número de opção da mensagem
 */
function extractOptionNumber(msg) {
  const cleaned = msg.trim().toLowerCase();

  // Direto é número
  if (/^[1-5]$/.test(cleaned)) return cleaned;

  // "5 outros", "1 trabalhar"
  const matchStart = cleaned.match(/^([1-5])\s+/);
  if (matchStart) return matchStart[1];

  // "opção 2", "opcao 3"
  const matchOption = cleaned.match(/op[cç][aã]o\s*([1-5])/i);
  if (matchOption) return matchOption[1];

  // Palavra para número
  const wordToNum = {
    'um': '1', 'uma': '1', 'primeiro': '1', 'primeira': '1', 'one': '1', 'first': '1',
    'dois': '2', 'duas': '2', 'segundo': '2', 'segunda': '2', 'two': '2', 'second': '2',
    'tres': '3', 'três': '3', 'terceiro': '3', 'terceira': '3', 'three': '3', 'third': '3',
    'quatro': '4', 'quarta': '4', 'four': '4', 'fourth': '4',
    'cinco': '5', 'quinta': '5', 'five': '5', 'fifth': '5',
    'outros': '5', 'outro': '5', 'outra': '5', 'other': '5', 'others': '5'
  };

  for (const [word, num] of Object.entries(wordToNum)) {
    if (cleaned === word || cleaned.startsWith(word + ' ')) return num;
  }

  return null;
}

/**
 * Processar mensagem do usuario
 */
function processMessage(message, currentState, leadData = {}, context = {}) {
  const msg = message ? message.trim() : '';
  const msgLower = msg.toLowerCase();

  // Detectar idioma pelo telefone (ou usar o já salvo)
  const lang = leadData.language || detectLanguage(context.phoneNumber) || 'en';
  const msgs = getMessages(lang);

  // Ignorar mensagens vazias
  if (shouldIgnoreMessage(msg)) {
    return {
      response: null,
      newState: currentState || STATES.NEW,
      data: { language: lang },
      shouldIgnore: true
    };
  }

  switch (currentState) {
    case STATES.NEW:
    case null:
    case undefined:
      return {
        response: msgs.welcome,
        newState: STATES.ASKED_NAME,
        data: { language: lang }
      };

    case STATES.ASKED_NAME:
      // SMART NAME DETECTION v8.4
      let name = null;

      // 1. Tentar extrair nome de padrão "meu nome é X"
      const extractedName = extractRealName(msg, lang);
      if (extractedName) {
        name = extractedName;
      }
      // 2. Verificar se a mensagem direta é um nome válido
      else if (isValidName(msg)) {
        name = formatName(msg);
      }
      // 3. Se não é nome válido, pedir novamente
      else {
        // Verificar se parece interesse de visto (para guardar)
        const visaKeywords = ['green card', 'visto', 'visa', 'cidadania', 'citizenship',
          'eb1', 'eb2', 'eb3', 'h1b', 'l1', 'o1', 'asilo', 'asylum', 'trabalho', 'work',
          'morar', 'trabalhar', 'investir', 'reunir', 'retornar', 'voltar'];
        const hasVisaInterest = visaKeywords.some(kw => msgLower.includes(kw));

        if (hasVisaInterest) {
          return {
            response: msgs.ask_name_again,
            newState: STATES.ASKED_NAME,
            data: {
              language: lang,
              _pending_interest: msg
            }
          };
        }

        // Qualquer outra coisa que não é nome - pedir novamente
        return {
          response: msgs.ask_name_again,
          newState: STATES.ASKED_NAME,
          data: { language: lang }
        };
      }

      // Validação final do nome
      if (!name || name.length < 2 || name.length > 50) {
        return {
          response: msgs.ask_name_again,
          newState: STATES.ASKED_NAME,
          data: { language: lang }
        };
      }

      // Se tinha interesse pendente, usar ele
      const pendingInterest = leadData._pending_interest;
      if (pendingInterest) {
        return {
          response: msgs.ask_email(pendingInterest),
          newState: STATES.ASKED_EMAIL,
          data: {
            client_name: name,
            visa_interest: pendingInterest,
            language: lang
          }
        };
      }

      return {
        response: msgs.ask_interest(name),
        newState: STATES.ASKED_INTEREST,
        data: { client_name: name, language: lang }
      };

    case STATES.ASKED_INTEREST:
      // Extrair número de opção se houver
      const optionNum = extractOptionNumber(msg);
      let interest;

      if (optionNum && msgs.interests[optionNum]) {
        interest = msgs.interests[optionNum];
      } else {
        interest = msgs.interests[msg] || msg;
      }

      return {
        response: msgs.ask_email(interest),
        newState: STATES.ASKED_EMAIL,
        data: { visa_interest: interest, language: lang }
      };

    case STATES.ASKED_EMAIL:
      const isSkip = msgs.skip_words.some(w => msgLower.includes(w));
      const email = isSkip ? null : extractEmail(msg);
      return {
        response: msgs.ask_consultation_type(leadData.client_name || 'friend'),
        newState: STATES.ASKED_CONSULTATION_TYPE,
        data: { email: email, language: lang }
      };

    case STATES.ASKED_CONSULTATION_TYPE:
      const consultOption = extractOptionNumber(msg) || msg;

      if (consultOption === '1') {
        return {
          response: null,
          newState: STATES.TRANSFERRED,
          data: { consultation_type: 'free', language: lang },
          action: 'send_free_consultation_email',
          shouldTransfer: true
        };
      } else if (consultOption === '2') {
        return {
          response: null,
          newState: STATES.AWAITING_PAYMENT,
          data: { consultation_type: 'paid', language: lang },
          action: 'generate_payment'
        };
      } else {
        return {
          response: msgs.invalid_consultation_choice,
          newState: STATES.ASKED_CONSULTATION_TYPE,
          data: { language: lang }
        };
      }

    case STATES.AWAITING_PAYMENT:
      if (msgLower === 'brl' || msgLower === 'reais' || msgLower === 'real') {
        return {
          response: null,
          newState: STATES.AWAITING_PAYMENT,
          data: { preferred_currency: 'brl', language: lang },
          action: 'generate_payment_brl'
        };
      } else if (msgLower === 'usd' || msgLower === 'dolar' || msgLower === 'dolares' || msgLower === 'dollar') {
        return {
          response: null,
          newState: STATES.AWAITING_PAYMENT,
          data: { preferred_currency: 'usd', language: lang },
          action: 'generate_payment_usd'
        };
      } else if (msgLower === '1' || msgLower.includes('gratu') || msgLower.includes('free') || msgLower.includes('gratis')) {
        return {
          response: null,
          newState: STATES.TRANSFERRED,
          data: { consultation_type: 'free', language: lang },
          action: 'send_free_consultation_email',
          shouldTransfer: true
        };
      } else {
        return {
          response: null,
          newState: STATES.AWAITING_PAYMENT,
          data: { language: lang },
          action: 'check_payment'
        };
      }

    case STATES.ASKED_SCHEDULING:
      const slotNumber = parseInt(msg);

      if (slotNumber >= 1 && slotNumber <= 10 && context.availableSlots) {
        const selectedSlot = context.availableSlots.find(s => s.number === slotNumber);
        if (selectedSlot) {
          return {
            response: null,
            newState: STATES.TRANSFERRED,
            data: {
              selected_slot: selectedSlot,
              scheduling_url: selectedSlot.scheduling_url,
              language: lang
            },
            action: 'confirm_scheduling',
            shouldTransfer: true
          };
        }
      }

      return {
        response: msgs.scheduling_invalid,
        newState: STATES.ASKED_SCHEDULING,
        data: { language: lang },
        action: 'show_times_again'
      };

    case STATES.TRANSFERRED:
      return {
        response: msgs.transferred,
        newState: STATES.TRANSFERRED,
        data: { language: lang },
        shouldTransfer: false
      };

    default:
      return {
        response: msgs.error,
        newState: STATES.NEW,
        data: { language: lang }
      };
  }
}

/**
 * Extrair nome da mensagem (legacy)
 */
function extractName(msg, lang = 'en') {
  const realName = extractRealName(msg, lang);
  if (realName) return realName;

  if (isValidName(msg)) {
    return formatName(msg);
  }

  const patterns = {
    pt: [
      /^(oi|olá|ola|hey|hi|hello|bom dia|boa tarde|boa noite|e aí|eai|opa)[,!\.\s]*/gi,
      /^(meu nome é|meu nome e|me chamo|sou o|sou a|eu sou|pode me chamar de)[:\s]*/gi,
      /^(tenho interesse|quero|gostaria|preciso)[^,]*/gi,
      /^(informações|informacoes|mais informações|por favor)[,!\.\s]*/gi
    ],
    en: [
      /^(hi|hello|hey|good morning|good afternoon|good evening)[,!\.\s]*/gi,
      /^(my name is|i am|i'm|call me|you can call me)[:\s]*/gi,
      /^(i'm interested|i want|i would like|i need)[^,]*/gi,
      /^(information|more information|please)[,!\.\s]*/gi
    ],
    es: [
      /^(hola|hey|hi|hello|buenos días|buenos dias|buenas tardes|buenas noches)[,!\.\s]*/gi,
      /^(mi nombre es|me llamo|soy|me pueden llamar)[:\s]*/gi,
      /^(tengo interés|tengo interes|quiero|quisiera|necesito)[^,]*/gi,
      /^(información|informacion|más información|por favor)[,!\.\s]*/gi
    ]
  };

  let name = msg;
  const langPatterns = patterns[lang] || patterns['en'];

  for (const pattern of langPatterns) {
    name = name.replace(pattern, '');
  }

  name = name.trim();

  const words = name.split(/\s+/);
  if (words.length > 3) {
    name = words.slice(0, 2).join(' ');
  }

  name = formatName(name);

  if (!name || name.length < 2) {
    const defaults = { pt: 'Amigo(a)', en: 'Friend', es: 'Amigo(a)' };
    return defaults[lang] || 'Friend';
  }

  return name;
}

/**
 * Extrair email da mensagem
 */
function extractEmail(msg) {
  const match = msg.match(/[\w.-]+@[\w.-]+\.\w+/);
  return match ? match[0].toLowerCase() : null;
}

/**
 * Verificar se e urgente
 */
function isUrgent(msg, lang = 'en') {
  const msgs = getMessages(lang);
  const lower = (msg || '').toLowerCase();
  return msgs.urgent_words.some(word => lower.includes(word));
}

/**
 * Gerar mensagem para consulta gratuita
 */
function generateFreeConsultationMessage(leadData = {}) {
  const lang = leadData.language || 'en';
  const msgs = getMessages(lang);
  return msgs.free_consultation_confirmed(leadData.client_name || 'friend');
}

/**
 * Gerar mensagem de horarios disponiveis
 */
function generateSchedulingMessage(slots, consultationType = 'paid', lang = 'en') {
  const msgs = getMessages(lang);

  if (!slots || slots.length === 0) {
    return msgs.scheduling_fallback;
  }

  return msgs.scheduling_prompt(slots);
}

/**
 * Gerar mensagem de confirmacao de agendamento
 */
function generateConfirmationMessage(slot, consultationType = 'paid', leadData = {}) {
  const lang = leadData.language || 'en';
  const msgs = getMessages(lang);
  return msgs.confirmation(
    leadData.client_name || 'friend',
    slot.display,
    slot.scheduling_url
  );
}

/**
 * Gerar mensagem de pagamento pendente
 */
function generatePaymentPendingMessage(lang = 'en') {
  const msgs = getMessages(lang);
  return msgs.payment_pending;
}

/**
 * Gerar mensagem de urgencia
 */
function generateUrgentMessage(lang = 'en') {
  const msgs = getMessages(lang);
  return msgs.urgent;
}

module.exports = {
  STATES,
  CONSULTATION_TYPES,
  NOT_A_NAME,
  NOT_A_NAME_PATTERNS,
  isValidName,
  extractRealName,
  formatName,
  extractOptionNumber,
  processMessage,
  extractName,
  extractEmail,
  isUrgent,
  shouldIgnoreMessage,
  generateFreeConsultationMessage,
  generateSchedulingMessage,
  generateConfirmationMessage,
  generatePaymentPendingMessage,
  generateUrgentMessage
};
