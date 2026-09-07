import { create } from "zustand";

interface User {
  id: string;
  name: string;
  email: string;
  role: "ADMIN" | "MAIN_ASSESSOR" | "ASSESSOR";
}

interface AuthState {
  user: User | null;
  token: string | null;
  login: (token: string, user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: {
    id: "00000000-0000-0000-0000-000000000001",
    name: "Sarah Johnson",
    email: "sarah.j@gradepro.ai",
    role: "ADMIN",
  },
  token: typeof window !== "undefined" ? localStorage.getItem("gradepro_token") : null,
  login: (token, user) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("gradepro_token", token);
    }
    set({ token, user });
  },
  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("gradepro_token");
    }
    set({ token: null, user: null });
  },
}));
