/**
 * Knowledge Base - WhatsApp Bot
 * CaseHub
 * Base de conhecimento completa sobre vistos e imigração americana
 */

// ==================== VISTOS DE TRABALHO ====================

const WORK_VISAS = {
  'H-1B': {
    nome: 'H-1B - Trabalho Especializado',
    descricao: 'Para profissionais com formação superior em áreas especializadas',
    requisitos: [
      'Graduação ou equivalente (bacharelado mínimo)',
      'Oferta de emprego de empresa americana',
      'Profissão que exija conhecimento especializado',
      'Salário compatível com o mercado'
    ],
    custo_uscis: '$1,710 base + $500 fraud fee + $2,805 premium (opcional)',
    taxa_empresa_grande: 'Empresas com 25+ funcionários H-1B: $4,000 adicional. Empresas 50+: até $100,000',
    tempo_processamento: '2-6 meses (premium processing: 15 dias úteis)',
    validade: '3 anos inicial, renovável até 6 anos total',
    loteria: 'Sim - registro em março, 65.000 vagas regulares + 20.000 para mestrado EUA',
    dicas: 'Loteria muito concorrida (25-30% de chance). Empresas patrocinadoras são responsáveis pelo processo.',
    brasileiros: 'Muito popular entre brasileiros de TI, engenharia e saúde'
  },

  'L-1A': {
    nome: 'L-1A - Transferência de Executivo/Gerente',
    descricao: 'Para executivos e gerentes transferidos dentro da mesma empresa',
    requisitos: [
      '1 ano trabalhando na empresa no exterior nos últimos 3 anos',
      'Cargo de executivo ou gerente',
      'Empresa deve ter operação nos EUA (ou estar abrindo)',
      'Função gerencial/executiva em ambos países'
    ],
    custo_uscis: '$1,385 + $500 fraud fee + taxas adicionais',
    tempo_processamento: '3-6 meses (premium disponível)',
    validade: '3 anos (novo escritório: 1 ano), renovável até 7 anos',
    loteria: 'Não - sem limite de vagas',
    dicas: 'Excelente opção para empresários que querem expandir para os EUA. Pode levar ao Green Card via EB-1C.',
    brasileiros: 'Muito usado por empresários brasileiros expandindo negócios'
  },

  'L-1B': {
    nome: 'L-1B - Conhecimento Especializado',
    descricao: 'Para funcionários com conhecimento especializado único da empresa',
    requisitos: [
      '1 ano na empresa no exterior',
      'Conhecimento especializado dos produtos/serviços/sistemas da empresa',
      'Conhecimento difícil de encontrar no mercado americano'
    ],
    custo_uscis: '$1,385 + $500 fraud fee',
    tempo_processamento: '3-6 meses',
    validade: '3 anos, renovável até 5 anos total',
    loteria: 'Não',
    dicas: 'Mais difícil de aprovar que L-1A. USCIS questiona frequentemente.',
    brasileiros: 'Usado por especialistas técnicos de empresas multinacionais'
  },

  'O-1': {
    nome: 'O-1 - Habilidade Extraordinária',
    descricao: 'Para pessoas com habilidade extraordinária em ciências, artes, educação, negócios ou esportes',
    requisitos: [
      'Reconhecimento nacional ou internacional sustentado',
      '3 de 8 critérios: prêmios, publicações, mídia, jurado, contribuições originais, artigos, exposições, salário alto'
    ],
    custo_uscis: '$1,055',
    tempo_processamento: '2-4 meses (premium disponível)',
    validade: '3 anos, renovável',
    loteria: 'Não',
    dicas: 'Não exige empregador, mas precisa de agente/patrocinador. Ótimo para artistas e empreendedores.',
    brasileiros: 'Popular entre artistas, atletas, chefs renomados e empresários de sucesso'
  },

  'E-2': {
    nome: 'E-2 - Investidor por Tratado',
    descricao: 'Para investidores de países com tratado comercial com os EUA',
    requisitos: [
      'Cidadania de país com tratado (Brasil NÃO tem, mas Itália/Portugal SIM)',
      'Investimento substancial ($100k+ recomendado)',
      'Negócio real e operacional',
      'Investidor deve dirigir/desenvolver o negócio'
    ],
    custo_uscis: '$695',
    tempo_processamento: '2-6 meses (consulado)',
    validade: '2-5 anos, renovável indefinidamente',
    loteria: 'Não',
    importante: 'BRASIL NÃO TEM TRATADO E-2. Brasileiros precisam de dupla cidadania (Itália, Portugal, etc.)',
    dicas: 'Investimento deve ser "substancial" - quanto menor o negócio, maior deve ser a % investida.',
    brasileiros: 'Muito procurado! Mas requer cidadania italiana, portuguesa ou de outro país com tratado'
  },

  'E-1': {
    nome: 'E-1 - Comerciante por Tratado',
    descricao: 'Para comerciantes de países com tratado que fazem comércio substancial com os EUA',
    requisitos: [
      'Cidadania de país com tratado',
      'Comércio substancial entre os dois países',
      '50%+ do comércio deve ser com os EUA'
    ],
    custo_uscis: '$695',
    tempo_processamento: '2-6 meses',
    validade: '2-5 anos, renovável',
    brasileiros: 'Mesmo problema do E-2: Brasil não tem tratado'
  }
};

// ==================== GREEN CARDS ====================

const GREEN_CARDS = {
  'EB-1A': {
    nome: 'EB-1A - Habilidade Extraordinária',
    categoria: 'Primeira Preferência',
    descricao: 'Green Card para pessoas com habilidade extraordinária comprovada',
    requisitos: [
      '3 de 10 critérios: prêmios reconhecidos, associações exclusivas, publicações sobre o candidato, jurado, contribuições originais, artigos acadêmicos, exposições, liderança, salário alto, sucesso comercial'
    ],
    custo_uscis: '$700 (I-140) + $1,225 (I-485) + taxas biométricas',
    tempo_processamento: '6-18 meses',
    fila_brasil: 'Sem fila - categoria atual',
    auto_peticao: 'Sim - não precisa de empregador',
    dicas: 'Padrão alto. Precisa documentar realizações excepcionais extensivamente.',
    brasileiros: 'Difícil mas possível para profissionais muito destacados'
  },

  'EB-1B': {
    nome: 'EB-1B - Pesquisador/Professor Extraordinário',
    categoria: 'Primeira Preferência',
    descricao: 'Para pesquisadores e professores com reconhecimento internacional',
    requisitos: [
      'Mínimo 3 anos de experiência em pesquisa/ensino',
      '2 de 6 critérios: prêmios, associações, publicações, jurado, contribuições, autoria de livros/artigos'
    ],
    custo_uscis: '$700 + $1,225',
    tempo_processamento: '6-18 meses',
    auto_peticao: 'Não - precisa de oferta de emprego permanente',
    brasileiros: 'Opção para acadêmicos brasileiros de destaque'
  },

  'EB-1C': {
    nome: 'EB-1C - Executivo/Gerente Multinacional',
    categoria: 'Primeira Preferência',
    descricao: 'Green Card para executivos/gerentes transferidos via L-1A',
    requisitos: [
      '1 ano como executivo/gerente na empresa no exterior',
      'Empresa deve estar operando nos EUA há pelo menos 1 ano',
      'Função executiva/gerencial permanente nos EUA'
    ],
    custo_uscis: '$700 + $1,225',
    tempo_processamento: '6-18 meses',
    auto_peticao: 'Não - empresa deve patrocinar',
    dicas: 'Caminho natural após L-1A. Empresa precisa demonstrar solidez.',
    brasileiros: 'Excelente para empresários brasileiros com operação nos EUA'
  },

  'EB-2-NIW': {
    nome: 'EB-2 NIW - National Interest Waiver',
    categoria: 'Segunda Preferência com Dispensa',
    descricao: 'Green Card para profissionais que beneficiam o interesse nacional americano',
    requisitos: [
      'Mestrado OU bacharelado + 5 anos experiência progressiva',
      'Área de trabalho com mérito substancial e importância nacional',
      'Candidato bem posicionado para avançar a área',
      'Benefício de dispensar oferta de emprego'
    ],
    custo_uscis: '$700 + $1,225',
    tempo_processamento: '12-24 meses',
    fila_brasil: 'Pequena fila atualmente (alguns meses)',
    auto_peticao: 'Sim - não precisa de empregador',
    alerta_2024: 'ATENÇÃO: USCIS mais rigoroso em 2024-2025. Taxa de RFE (Request for Evidence) aumentou significativamente. Mais negações.',
    dicas: 'Caso deve ser muito bem documentado. Cartas de recomendação fortes são essenciais. Tendência de maior escrutínio.',
    brasileiros: 'Muito popular entre brasileiros de TI, medicina, engenharia. Mas prepare-se para processo mais difícil.'
  },

  'EB-2-PERM': {
    nome: 'EB-2 via PERM',
    categoria: 'Segunda Preferência com Labor Certification',
    descricao: 'Green Card para profissionais com mestrado via processo de certificação trabalhista',
    requisitos: [
      'Mestrado OU bacharelado + 5 anos experiência',
      'Oferta de emprego permanente',
      'Empregador prova que não há americanos qualificados (PERM)'
    ],
    custo_uscis: '$700 + $1,225 + custos PERM',
    tempo_processamento: '18-36 meses total',
    fila_brasil: 'Pequena fila',
    dicas: 'Processo mais longo por causa do PERM, mas requisitos técnicos mais claros.',
    brasileiros: 'Boa opção se tiver empregador disposto a patrocinar'
  },

  'EB-3': {
    nome: 'EB-3 - Trabalhadores Qualificados',
    categoria: 'Terceira Preferência',
    descricao: 'Green Card para trabalhadores qualificados, profissionais e outros',
    requisitos: [
      'Qualificados: 2+ anos experiência',
      'Profissionais: bacharelado',
      'Outros: menos de 2 anos experiência',
      'Todos precisam de PERM e oferta de emprego'
    ],
    custo_uscis: '$700 + $1,225',
    tempo_processamento: '24-48 meses',
    fila_brasil: 'Fila moderada para qualificados/profissionais, longa para "outros"',
    brasileiros: 'Opção viável mas processo longo'
  },

  'EB-5': {
    nome: 'EB-5 - Investidor Imigrante',
    categoria: 'Quinta Preferência',
    descricao: 'Green Card através de investimento e criação de empregos',
    requisitos: [
      '$800,000 em área TEA (Targeted Employment Area) OU $1,050,000 investimento direto',
      'Criar mínimo 10 empregos em tempo integral',
      'Capital deve ser de origem lícita comprovada',
      'Investidor deve participar ativamente'
    ],
    custo_uscis: '$3,675 + $1,225 + custos de investimento',
    tempo_processamento: '24-36+ meses',
    fila_brasil: 'Sem fila significativa',
    dicas: 'Regional Centers facilitam criação de empregos. Due diligence do projeto é crucial.',
    brasileiros: 'Opção para brasileiros com capital disponível. Cuidado com projetos fraudulentos.'
  },

  'GREEN-CARD-FAMILIAR': {
    nome: 'Green Card por Família',
    categoria: 'Imigração Familiar',
    tipos: {
      'Imediato': {
        descricao: 'Cônjuge, filho solteiro menor de 21, ou pai/mãe de cidadão americano',
        tempo: '12-24 meses',
        fila: 'Sem limite de vagas'
      },
      'F1': {
        descricao: 'Filho solteiro adulto de cidadão americano',
        tempo: '7-10 anos',
        fila: 'Longa'
      },
      'F2A': {
        descricao: 'Cônjuge ou filho menor de residente permanente',
        tempo: '2-3 anos',
        fila: 'Moderada'
      },
      'F2B': {
        descricao: 'Filho solteiro adulto de residente permanente',
        tempo: '5-7 anos',
        fila: 'Longa'
      },
      'F3': {
        descricao: 'Filho casado de cidadão americano',
        tempo: '12-15 anos',
        fila: 'Muito longa'
      },
      'F4': {
        descricao: 'Irmão de cidadão americano',
        tempo: '15-20 anos',
        fila: 'Extremamente longa'
      }
    },
    dicas: 'Categoria imediata é a mais rápida. Filas podem mudar com políticas de imigração.',
    brasileiros: 'Se tiver familiar cidadão americano, pode ser a melhor opção dependendo do parentesco'
  }
};

// ==================== OUTROS VISTOS ====================

const OTHER_VISAS = {
  'K-1': {
    nome: 'K-1 - Visto de Noivo(a)',
    descricao: 'Para noivos de cidadãos americanos entrarem nos EUA para casar',
    requisitos: [
      'Noivado com cidadão americano',
      'Encontro presencial nos últimos 2 anos (com exceções)',
      'Intenção genuína de casar em 90 dias',
      'Ambos legalmente aptos a casar'
    ],
    custo_uscis: '$535 (I-129F) + taxas consulares',
    tempo_processamento: '12-18 meses',
    validade: '90 dias para casar após entrada',
    dicas: 'Após casamento, solicita Adjustment of Status para Green Card.',
    brasileiros: 'Popular para brasileiros em relacionamento com americanos'
  },

  'B-1-B-2': {
    nome: 'B-1/B-2 - Turismo e Negócios',
    descricao: 'Visto de visitante para turismo ou negócios temporários',
    requisitos: [
      'Vínculos fortes com país de origem (emprego, família, propriedade)',
      'Fundos suficientes para a viagem',
      'Intenção de retornar',
      'Propósito legítimo da viagem'
    ],
    custo: '$185 (taxa consular)',
    tempo_processamento: 'Entrevista em dias/semanas',
    validade: 'Visto: 10 anos. Estadia: até 6 meses por entrada',
    importante: 'NÃO PERMITE TRABALHO. Violação pode resultar em deportação e banimento.',
    taxa_negacao_brasil: 'Relativamente alta para jovens solteiros sem vínculos fortes',
    dicas: 'Documentar vínculos é essencial. Emprego estável, imóveis, família dependente ajudam.',
    brasileiros: 'Negativas são comuns. Prepare-se bem para a entrevista consular.'
  },

  'F-1': {
    nome: 'F-1 - Estudante',
    descricao: 'Para estudos acadêmicos em tempo integral',
    requisitos: [
      'Aceite em instituição certificada SEVP',
      'Comprovação de fundos para custear estudos e vida',
      'Vínculos com país de origem',
      'Proficiência em inglês (se aplicável)'
    ],
    custo: '$185 (taxa consular) + $350 SEVIS',
    tempo_processamento: 'Entrevista em semanas',
    trabalho: 'OPT: 12 meses após formatura (STEM: 36 meses). CPT: durante estudos relacionados.',
    dicas: 'OPT pode ser ponte para H-1B. Escolha instituição e curso estrategicamente.',
    brasileiros: 'Bom caminho para quem quer ganhar experiência americana'
  },

  'J-1': {
    nome: 'J-1 - Visitante de Intercâmbio',
    descricao: 'Para programas de intercâmbio aprovados',
    categorias: 'Au pair, trainee, intern, professor, pesquisador, médico, etc.',
    custo: '$185 + $220 SEVIS',
    tempo_processamento: 'Variável',
    cuidado: 'Algumas categorias têm requisito de retorno ao país de origem por 2 anos (212e)',
    brasileiros: 'Popular para trainee e au pair. Verifique se há requisito de retorno.'
  },

  'TN': {
    nome: 'TN - USMCA (antigo NAFTA)',
    descricao: 'Para profissionais do Canadá e México',
    importante: 'NÃO DISPONÍVEL PARA BRASILEIROS',
    brasileiros: 'Não aplicável'
  }
};

// ==================== INFORMAÇÕES DO ESCRITÓRIO ====================

const SOBRE_ESCRITORIO = {
  nome: '${process.env.ORG_NAME || "CaseHub"}',
  fundador: {
    nome: 'nosso advogado',
    titulo: 'Attorney at Law',
    credenciais: [
      'Advogado licenciado na Califórnia (Bar #326677)',
      'Mestre em Direito de Imigração',
      'Treinamento pela AILA (American Immigration Lawyers Association)',
      'Licenciado pela OAB Brasil'
    ],
    experiencia: 'Advogado de imigração desde 2017, prática nos EUA desde 2018',
    diferencial: 'Imigrante brasileiro que viveu a jornada - entende as dificuldades pessoalmente'
  },
  localizacoes: [
    'Glendale, California (sede)',
    'Sheridan, Wyoming',
    'Capão da Canoa, Rio Grande do Sul, Brasil'
  ],
  contato: {
    telefone: '+1 (940) 619-5856',
    email: (process.env.ORG_EMAIL || 'info@casehub.app'),
    website: (process.env.ORG_WEBSITE || 'https://casehub.app'),
    agendamento: '${process.env.ORG_WEBSITE || "https://casehub.app"}/consulta'
  },
  idiomas: ['Português', 'Inglês', 'Espanhol'],
  diferenciais: [
    'De imigrante para imigrante - equipe que viveu a experiência',
    'Atendimento personalizado e sem surpresas',
    'Consulta mundial via teleconsulta',
    'Especialistas em casos complexos e previamente negados',
    '100% avaliações 5 estrelas (Avvo, Google, Birdeye)',
    'Metodologia: questionário detalhado -> pesquisa -> múltiplas opções personalizadas'
  ],
  especialidades: [
    'Visto E-2 para investidores',
    'EB-2 NIW (National Interest Waiver)',
    'Green Cards em situações complexas',
    'Reunificação familiar',
    'Casos previamente negados'
  ],
  avaliacoes: {
    avvo: '5 estrelas - 11 reviews',
    google: '5 estrelas',
    birdeye: '5 estrelas - 27 reviews',
    destaque: '100% de avaliações 5 estrelas'
  },
  metodologia: {
    passo1: 'Questionário detalhado para entender sua situação',
    passo2: 'Pesquisa aprofundada do caso',
    passo3: 'Consulta com apresentação de múltiplas opções',
    passo4: 'Acompanhamento em todas as etapas do processo'
  }
};

// ==================== CONTEXTO 2024-2025 ====================

const CONTEXTO_ATUAL = {
  ano: '2024-2025',
  alertas: [
    {
      visto: 'H-1B',
      alerta: 'Nova taxa de $100,000 para empresas grandes com alto percentual de funcionários H-1B',
      impacto: 'Menos empresas dispostas a patrocinar'
    },
    {
      visto: 'EB-2 NIW',
      alerta: 'USCIS significativamente mais rigoroso. Taxa de RFE (Request for Evidence) aumentou. Mais negações.',
      impacto: 'Casos precisam ser muito mais fortes e bem documentados'
    },
    {
      visto: 'E-2',
      alerta: 'Brasil continua sem tratado. Brasileiros precisam de dupla cidadania.',
      impacto: 'Itália e Portugal são as cidadanias mais comuns'
    },
    {
      geral: 'Processamento',
      alerta: 'Tempos de processamento aumentaram em várias categorias devido ao volume alto',
      impacto: 'Planejar com antecedência é mais importante que nunca'
    }
  ],
  tendencias: [
    'USCIS mais rigoroso em geral',
    'Maior escrutínio de petições de emprego',
    'Premium processing expandido para mais categorias',
    'Foco em imigração baseada em mérito'
  ]
};

// ==================== PERGUNTAS FREQUENTES ====================

const FAQ = {
  'quanto_custa': {
    pergunta: 'Quanto custa o processo?',
    resposta: 'Os custos variam muito dependendo do tipo de visto. Há taxas governamentais (USCIS, consulado) e honorários advocatícios. Na consulta, nosso advogado apresenta todos os custos detalhadamente para seu caso específico.'
  },
  'quanto_tempo': {
    pergunta: 'Quanto tempo demora?',
    resposta: 'Depende do tipo de visto: H-1B (2-6 meses), Green Card EB-2 NIW (12-24 meses), K-1 (12-18 meses). Cada caso é único e na consulta podemos dar uma estimativa mais precisa.'
  },
  'posso_trabalhar': {
    pergunta: 'Posso trabalhar com visto de turista?',
    resposta: 'Não. O visto B-1/B-2 NÃO permite trabalho. Trabalhar com visto de turista é violação grave que pode resultar em deportação e banimento dos EUA.'
  },
  'sem_ingles': {
    pergunta: 'Preciso falar inglês?',
    resposta: 'Depende do visto. Para trabalho (H-1B, L-1), geralmente sim. Para investidor (E-2), não necessariamente. Para Green Card EB, depende da área. Atendemos em português!'
  },
  'brasil_e2': {
    pergunta: 'Brasileiro pode tirar E-2?',
    resposta: 'Diretamente não, porque Brasil não tem tratado com os EUA para E-2. Mas brasileiros com dupla cidadania (italiana, portuguesa, etc.) podem solicitar pelo outro país.'
  },
  'negado_antes': {
    pergunta: 'Fui negado antes, tenho chance?',
    resposta: 'Sim! Nosso advogado é especialista em casos previamente negados. Cada caso precisa ser analisado para entender o motivo da negação e como fortalecer uma nova petição.'
  }
};

// ==================== EXPORTAÇÃO ====================

module.exports = {
  WORK_VISAS,
  GREEN_CARDS,
  OTHER_VISAS,
  SOBRE_ESCRITORIO,
  CONTEXTO_ATUAL,
  FAQ,

  // Função helper para buscar informações de visto
  getVisaInfo: function(visaType) {
    const type = visaType.toUpperCase().replace(/ /g, '-');
    return WORK_VISAS[type] || GREEN_CARDS[type] || OTHER_VISAS[type] || null;
  }
};
