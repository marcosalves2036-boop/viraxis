const API_URL = "/api";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  full_name: string;
}

export interface MessageResponse {
  message: string;
}

export interface ApiError {
  detail: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error((data as ApiError).detail ?? "Erro desconhecido");
  }
  return data as T;
}

export const api = {
  register: (email: string, password: string, full_name: string) =>
    post<MessageResponse>("/auth/register", { email, password, full_name }),

  verifyEmail: (token: string) =>
    post<MessageResponse>("/auth/verify-email", { token }),

  resendVerification: (email: string) =>
    post<MessageResponse>("/auth/resend-verification", { email }),

  login: (email: string, password: string) =>
    post<TokenResponse>("/auth/login", { email, password }),
};

// Token helpers (localStorage — troca por httpOnly cookie em prod)
export const auth = {
  save: (token: TokenResponse) => {
    localStorage.setItem("viraxis_token", token.access_token);
    localStorage.setItem("viraxis_user", JSON.stringify({
      id: