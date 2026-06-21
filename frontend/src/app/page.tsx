import Link from "next/link";

// ─── Navbar ──────────────────────────────────────────────────────────────────
function Navbar() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-white/[0.06] backdrop-blur-md bg-[#06070a]/80">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <span className="text-xl font-bold tracking-tight gradient-text">
          VIRAXIS
        </span>
        <nav className="hidden md:flex items-center gap-8 text-sm text-white/60">
          <a href="#como-funciona" className="hover:text-white transition-colors">Como funciona</a>
          <a href="#agentes" className="hover:text-white transition-colors">Agentes</a>
          <a href="#precos" className="hover:text-white transition-colors">Preços</a>
        </nav>
        <div className="flex items-center gap-3">
          <Link href="/login" className="text-sm text-white/60 hover:text-white transition-colors px-4 py-2">
            Entrar
          </Link>
          <Link href="/cadastro" className="text-sm bg-violet-600 hover:bg-violet-500 text-white px-4 py-2 rounded-lg transition-colors font-medium">
            Começar grátis
          </Link>
        </div>
      </div>
    </header>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-16">
      {/* Background glows */}
      <div className="hero-glow w-[600px] h-[600px] bg-violet-600" style={{ top: "10%", left: "50%", transform: "translateX(-50%)" }} />
      <div className="hero-glow w-[400px] h-[400px] bg-cyan-500" style={{ top: "40%", right: "5%" }} />
      <div className="hero-glow w-[300px] h-[300px] bg-violet-800" style={{ bottom: "10%", left: "5%" }} />
      {/* Grid texture */}
      <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)", backgroundSize: "40px 40px" }} />

      <div className="relative z-10 text-center max-w-4xl mx-auto px-6">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-300 text-sm mb-8">
          <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
          Fase Beta — vagas limitadas
        </div>

        <h1 className="text-5xl md:text-7xl font-black tracking-tight leading-[1.05] mb-6">
          Seu Escritório de{" "}
          <span className="gradient-text">Conteúdo Viral</span>
          <br />
          no piloto automático.
        </h1>

        <p className="text-lg md:text-xl text-white/50 max-w-2xl mx-auto mb-10 leading-relaxed">
          Agentes de IA que analisam tendências, decidem o que criar, escrevem os scripts,
          editam os vídeos e publicam — enquanto você dorme. Cada decisão documentada
          com hipótese e reasoning auditável.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link href="/cadastro" className="w-full sm:w-auto px-8 py-4 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl transition-all glow-violet hover:scale-[1.02] active:scale-[0.98]">
            Criar meu escritório grátis
          </Link>
          <Link href="#como-funciona" className="w-full sm:w-auto px-8 py-4 border border-white/10 hover:border-white/20 text-white/70 hover:text-white font-medium rounded-xl transition-all">
            Ver como funciona →
          </Link>
        </div>

        <p className="mt-10 text-sm text-white/30">
          Sem cartão de crédito · Escritório ativo em 5 minutos · Cancele quando quiser
        </p>
      </div>
    </section>
  );
}

// ─── Stats Bar ────────────────────────────────────────────────────────────────
function StatsBar() {
  const stats = [
    { value: "24/7", label: "Operação contínua" },
    { value: "4", label: "Agentes autônomos" },
    { value: "100%", label: "Decisões auditáveis" },
    { value: "0", label: "Horas de edição manual" },
  ];
  return (
    <section className="border-y border-white/[0.06] bg-white/[0.02]">
      <div className="max-w-6xl mx-auto px-6 py-12 grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
        {stats.map((s) => (
          <div key={s.label}>
            <p className="text-4xl font-black gradient-text mb-1">{s.value}</p>
            <p className="text-sm text-white/40">{s.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ─── How It Works ─────────────────────────────────────────────────────────────
function HowItWorks() {
  const steps = [
    {
      number: "01", agent: "BRAIN", color: "violet",
      title: "Decide o que criar",
      description: "Analisa o perfil do nicho, identifica os archetypes de maior performance e formula uma hipótese estratégica com confidence score. Cada decisão tem reasoning documentado.",
      tags: ["Análise de nicho", "Hipótese", "Confiança 0–100%"],
    },
    {
      number: "02", agent: "SCOUT", color: "cyan",
      title: "Rastreia tendências em tempo real",
      description: "Monitora TikTok, YouTube Shorts e Google Trends continuamente. Alimenta o BRAIN com sinais frescos de mercado para que cada decisão seja baseada em dados reais.",
      tags: ["TikTok trends", "YouTube Shorts", "Google Trends"],
    },
    {
      number: "03", agent: "WRITER", color: "emerald",
      title: "Escreve o script viral",
      description: "Recebe a decisão do BRAIN e produz um script otimizado para o formato, plataforma e archetype escolhido — com gancho, desenvolvimento e CTA na medida certa.",
      tags: ["Script 30–60s", "Gancho viral", "CTA otimizado"],
    },
    {
      number: "04", agent: "PUBLISHER", color: "orange",
      title: "Publica e escala",
      description: "Edita o vídeo, adiciona legendas e publica automaticamente nas plataformas configuradas. Registra métricas de performance para retroalimentar o BRAIN.",
      tags: ["Auto-edição", "Multi-plataforma", "Métricas automáticas"],
    },
  ];

  const colorMap: Record<string, string> = {
    violet: "border-violet-500/30 bg-violet-500/10 text-violet-300",
    cyan: "border-cyan-500/30 bg-cyan-500/10 text-cyan-300",
    emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    orange: "border-orange-500/30 bg-orange-500/10 text-orange-300",
  };

  const dotMap: Record<string, string> = {
    violet: "bg-violet-500", cyan: "bg-cyan-500",
    emerald: "bg-emerald-500", orange: "bg-orange-500",
  };

  return (
    <section id="como-funciona" className="py-32 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-20">
          <p className="text-sm text-violet-400 font-semibold tracking-widest uppercase mb-3">Pipeline autônomo</p>
          <h2 className="text-4xl md:text-5xl font-black tracking-tight mb-4">Como o escritório funciona</h2>
          <p className="text-white/50 max-w-xl mx-auto">
            Quatro agentes especializados trabalhando em loop contínuo. Você configura o nicho uma vez — eles operam para sempre.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          {steps.map((step) => (
            <div key={step.agent} className="card-glass rounded-2xl p-8 hover:border-white/[0.12] transition-colors group">
              <div className="flex items-start justify-between mb-6">
                <span className="text-5xl font-black text-white/10 group-hover:text-white/15 transition-colors">{step.number}</span>
                <span className={`px-3 py-1 rounded-full text-xs font-bold border ${colorMap[step.color]}`}>{step.agent}</span>
              </div>
              <h3 className="text-xl font-bold mb-3">{step.title}</h3>
              <p className="text-white/50 text-sm leading-relaxed mb-6">{step.description}</p>
              <div className="flex flex-wrap gap-2">
                {step.tags.map((tag) => (
                  <span key={tag} className="flex items-center gap-1.5 text-xs text-white/40 bg-white/[0.04] px-3 py-1 rounded-full">
                    <span className={`w-1.5 h-1.5 rounded-full ${dotMap[step.color]}`} />
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Features ─────────────────────────────────────────────────────────────────
function Features() {
  const features = [
    { icon: "🧠", title: "Decisões auditáveis", description: "O BRAIN documenta cada escolha — hipótese, evidências, alternativas descartadas e confidence score. Você sabe exatamente por que cada vídeo foi criado." },
    { icon: "📊", title: "Aprende com performance", description: "Cada publicação retroalimenta o sistema. Com o tempo, o escritório aprende o que funciona no seu nicho específico e melhora continuamente." },
    { icon: "🔄", title: "Multi-plataforma nativo", description: "TikTok, Instagram Reels, YouTube Shorts e mais. O WRITER adapta o script e o PUBLISHER entrega no formato certo para cada plataforma." },
    { icon: "🛡️", title: "Multi-tenant seguro", description: "Cada escritório é completamente isolado. Seus dados, nichos e estratégias não são compartilhados com nenhum outro usuário." },
    { icon: "⚡", title: "Troca de modelo em 1 linha", description: "Gemini, GPT-4, Claude, Llama — o provider de IA é configurável. Você não fica preso a nenhum fornecedor." },
    { icon: "📈", title: "Dashboard em tempo real", description: "Veja as decisões do BRAIN, status dos conteúdos, métricas de performance e o raciocínio por trás de cada escolha — tudo em um só lugar." },
  ];

  return (
    <section id="agentes" className="py-32 px-6 border-t border-white/[0.06]">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-20">
          <p className="text-sm text-cyan-400 font-semibold tracking-widest uppercase mb-3">Diferenciais</p>
          <h2 className="text-4xl md:text-5xl font-black tracking-tight mb-4">Por que VIRAXIS?</h2>
          <p className="text-white/50 max-w-xl mx-auto">
            Não é só uma ferramenta de geração de conteúdo. É um sistema de inteligência operacional que documenta e aprende.
          </p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((f) => (
            <div key={f.title} className="card-glass rounded-2xl p-6 hover:border-white/[0.12] transition-colors">
              <span className="text-3xl mb-4 block">{f.icon}</span>
              <h3 className="font-bold text-base mb-2">{f.title}</h3>
              <p className="text-sm text-white/45 leading-relaxed">{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Pricing ──────────────────────────────────────────────────────────────────
function Pricing() {
  const plans = [
    {
      name: "Starter", price: "Grátis", period: "",
      description: "Para testar o escritório",
      features: ["1 escritório virtual", "10 decisões do BRAIN/mês", "Publicação manual", "Dashboard básico"],
      cta: "Começar grátis", highlight: false,
    },
    {
      name: "Pro", price: "R$ 97", period: "/mês",
      description: "Para criadores sérios",
      features: ["5 escritórios virtuais", "Decisões ilimitadas", "Publicação automática", "SCOUT em tempo real", "Histórico de decisions", "Suporte prioritário"],
      cta: "Assinar Pro", highlight: true,
    },
    {
      name: "Business", price: "R$ 297", period: "/mês",
      description: "Para agências e times",
      features: ["Escritórios ilimitados", "Multi-usuário", "API access", "White-label (em breve)", "Onboarding dedicado", "SLA 99.9%"],
      cta: "Falar com vendas", highlight: false,
    },
  ];

  return (
    <section id="precos" className="py-32 px-6 border-t border-white/[0.06]">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-20">
          <p className="text-sm text-violet-400 font-semibold tracking-widest uppercase mb-3">Preços</p>
          <h2 className="text-4xl md:text-5xl font-black tracking-tight mb-4">Simples e previsível</h2>
          <p className="text-white/50">Comece grátis, escale quando precisar.</p>
        </div>
        <div className="grid md:grid-cols-3 gap-6">
          {plans.map((plan) => (
            <div key={plan.name} className={`rounded-2xl p-8 flex flex-col relative ${plan.highlight ? "bg-violet-600/20 border border-violet-500/50 glow-violet" : "card-glass"}`}>
              {plan.highlight && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-violet-600 text-white text-xs font-bold rounded-full">
                  Mais popular
                </span>
              )}
              <div className="mb-6">
                <p className="text-sm text-white/50 mb-1">{plan.name}</p>
                <div className="flex items-end gap-1">
                  <span className="text-4xl font-black">{plan.price}</span>
                  {plan.period && <span className="text-white/40 mb-1">{plan.period}</span>}
                </div>
                <p className="text-sm text-white/40 mt-1">{plan.description}</p>
              </div>
              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-white/70">
                    <span className="text-violet-400">✓</span>{f}
                  </li>
                ))}
              </ul>
              <Link href="#" className={`text-center py-3 rounded-xl font-semibold text-sm transition-all ${plan.highlight ? "bg-violet-600 hover:bg-violet-500 text-white" : "border border-white/10 hover:border-white/20 text-white/70 hover:text-white"}`}>
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── CTA Final ────────────────────────────────────────────────────────────────
function CTAFinal() {
  return (
    <section className="py-32 px-6 border-t border-white/[0.06]">
      <div className="max-w-3xl mx-auto text-center relative">
        <div className="hero-glow w-[500px] h-[300px] bg-violet-600" style={{ top: "50%", left: "50%", transform: "translate(-50%, -50%)" }} />
        <div className="relative z-10">
          <h2 className="text-4xl md:text-6xl font-black tracking-tight mb-6">
            Pronto para ativar seu{" "}
            <span className="gradient-text">escritório viral?</span>
          </h2>
          <p className="text-white/50 text-lg mb-10">Configure uma vez. Deixe os agentes trabalharem.</p>
          <Link href="#" className="inline-block px-10 py-4 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl transition-all glow-violet hover:scale-[1.02] active:scale-[0.98] text-lg">
            Criar meu escritório grátis
          </Link>
          <p className="mt-5 text-sm text-white/25">Sem cartão de crédito · Escritório ativo em 5 minutos</p>
        </div>
      </div>
    </section>
  );
}

// ─── Footer ───────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="border-t border-white/[0.06] py-10 px-6">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <span className="font-bold tracking-tight gradient-text">VIRAXIS</span>
        <p className="text-sm text-white/25">© 2026 VIRAXIS. Todos os direitos reservados.</p>
        <div className="flex gap-6 text-sm text-white/30">
          <a href="#" className="hover:text-white/60 transition-colors">Privacidade</a>
          <a href="#" className="hover:text-white/60 transition-colors">Termos</a>
          <a href="#" className="hover:text-white/60 transition-colors">Contato</a>
        </div>
      </div>
    </footer>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <StatsBar />
        <HowItWorks />
        <Features />
        <Pricing />
        <CTAFinal />
      </main>
      <Footer />
    </>
  );
}
