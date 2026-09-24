export interface AuthUser {
  id_usuario: number;
  nombre: string;
  apellido: string;
  usuario: string;
  telefono: string | null;
}

export interface LoginResponse {
  ok: boolean;
  usuario?: AuthUser;
  mensaje?: string;
}

export interface RegistroResponse {
  ok: boolean;
  mensaje: string;
}
