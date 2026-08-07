"use client";

/**
 * Estado vazio da Biblioteca — extraído de `dashboard/biblioteca/page.tsx`
 * (item P2 do BACKLOG, `fonte: arthur`). Comportamento e cópia 100%
 * preservados: CTA "Enviar primeiro vídeo" dispara o mesmo input de upload
 * do card "+" do grid, desabilitado enquanto `uploading` ou sem escritório
 * selecionado, com aviso inline nesse segundo caso.
 */

interface EmptyStateProps {
  onUploadClick: () => void;
  uploading: boolean;
  hasOffice: boolean;
}

export default function EmptyState({ onUploadClick, uploading, hasOffice }: EmptyStateProps) {
  return (
    <div className="card-glass rounded-2xl p-12 text-center space-y-4">
      <div className="text-6xl">🎬</div>
      <div className="space-y-1.5">
        <p className="text-white/70 text-lg font-semibold">Sua biblioteca está vazia</p>
        <p className="text-white/35 text-sm max-w-sm mx-auto">
          Envie vídeos brutos para que a IA analise cenas, transcrição e destaques
          automaticamente — sem precisar clicar em nada depois do upload.
        </p>
      </div>
      <button
        onClick={onUploadClick}
        disabled={uploading || !hasOffice}
        className="inline-flex items-center gap-2 px-5 py-3 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold transition-colors"
      >
        <span className="text-base">▲</span> Enviar primeiro vídeo
      </button>
      {!hasOffice && (
        <p className="text-white/25 text-xs">Selecione um escritório acima para habilitar o upload.</p>
      )}
    </div>
  );
}
