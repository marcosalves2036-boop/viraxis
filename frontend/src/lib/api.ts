const API_URL = "/api";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  full_name: string;
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
    post<TokenResponse>("/auth/register", { email, password, full_name }),

  login: (email: string, password: string) =>
    post<TokenResponse>("/auth/login", { email, password }),
};

// Token helpers (localStorage — troca por httpOnly cookie em prod)
export const auth = {
  save: (token: TokenResponse) => {
    localStorage.setItem("viraxis_token", token.access_token);
    localStorage.setItem("viraxis_user", JSON.stringify({
      id: token.user_id,
      email: token.email,
      full_name: token.full_name,
    }));
  },
  clear: () => {
    localStorage.removeItem("viraxis_token");
    localStorage.removeItem("viraxis_user");
  },
  getToken: () => localStorage.getItem("viraxis_token"),
};
