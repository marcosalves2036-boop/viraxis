import { redirect } from "next/navigation";

// Rota consolidada em /dashboard/analytics (aba "Decisões Editoriais").
// Mantida para não quebrar links e favoritos antigos.
export default function AnaliticosRedirect() {
  redirect("/dashboard/analytics?tab=decisoes");
}
