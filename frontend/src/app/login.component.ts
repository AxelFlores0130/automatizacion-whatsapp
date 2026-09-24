import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from './auth.service';

@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-login',
  styleUrl: './auth-page.scss',
  templateUrl: './login.component.html',
})
export class LoginComponent {
  private readonly formBuilder = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly form = this.formBuilder.nonNullable.group({
    usuario: ['', Validators.required],
    contrasena: ['', Validators.required],
    recordarme: [false],
  });
  protected readonly passwordVisible = signal(false);
  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal('');

  protected submit(): void {
    this.errorMessage.set('');
    this.form.markAllAsTouched();
    if (this.form.invalid || this.submitting()) {
      return;
    }

    const { usuario, contrasena, recordarme } = this.form.getRawValue();
    this.submitting.set(true);
    this.auth
      .login({ usuario, contrasena }, recordarme)
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: () => void this.router.navigate(['/transferencias']),
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(this.errorForStatus(error.status));
        },
      });
  }

  protected togglePassword(): void {
    this.passwordVisible.update((visible) => !visible);
  }

  private errorForStatus(status: number): string {
    if (status === 401) {
      return 'Usuario o contraseña incorrectos.';
    }
    if (status === 403) {
      return 'Tu usuario se encuentra inactivo. Contacta al administrador.';
    }
    if (status === 0) {
      return 'No fue posible conectar con el servidor.';
    }
    return 'No fue posible iniciar sesión.';
  }
}
