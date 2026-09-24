import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { AuthUser, LoginResponse, RegistroResponse } from './auth.model';

interface LoginCredentials {
  usuario: string;
  contrasena: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://127.0.0.1:5000/api/auth';
  private readonly storageKey = 'dorian-auth-user';

  login(credentials: LoginCredentials, recordar: boolean): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.apiUrl}/login`, credentials).pipe(
      tap((response) => {
        if (response.ok && response.usuario) {
          this.saveUser(response.usuario, recordar);
        }
      }),
    );
  }

  registro(datos: {
    nombre: string;
    apellido: string;
    telefono: string;
    usuario: string;
    contrasena: string;
  }): Observable<RegistroResponse> {
    return this.http.post<RegistroResponse>(`${this.apiUrl}/registro`, datos);
  }

  logout(): void {
    sessionStorage.removeItem(this.storageKey);
    localStorage.removeItem(this.storageKey);
  }

  isAuthenticated(): boolean {
    return this.getCurrentUser() !== null;
  }

  getCurrentUser(): AuthUser | null {
    return this.readUser(sessionStorage) ?? this.readUser(localStorage);
  }

  private saveUser(user: AuthUser, recordar: boolean): void {
    this.logout();
    const storage = recordar ? localStorage : sessionStorage;
    storage.setItem(this.storageKey, JSON.stringify(user));
  }

  private readUser(storage: Storage): AuthUser | null {
    const serialized = storage.getItem(this.storageKey);
    if (!serialized) {
      return null;
    }

    try {
      const user = JSON.parse(serialized) as AuthUser;
      return user?.id_usuario && user.usuario ? user : null;
    } catch {
      storage.removeItem(this.storageKey);
      return null;
    }
  }
}
