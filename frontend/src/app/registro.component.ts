import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from './auth.service';

@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-registro',
  styleUrl: './auth-page.scss',
  templateUrl: './registro.component.html',
})
export class RegistroComponent {
  private readonly formBuilder = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly form = this.formBuilder.nonNullable.group({
    nombre: ['', Validators.required],
    apellido: ['', Validators.required],
    telefono: [''],
    usuario: ['', Validators.required],
    contrasena: ['', Validators.required],
    confirmarContrasena: ['', Validators.required],
  });
  protected readonly passwordVisible = signal(false);
  protected readonly confirmPasswordVisible = signal(false);
  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal('');
  protected readonly successMessage = signal('');

  protected submit(): void {
    this.errorMessage.set('');
    this.successMessage.set('');
    this.form.markAllAsTouched();
    if (this.form.invalid || this.submitting()) {
      return;
    }

    const { nombre, apellido, telefono, usuario, contrasena, confirmarContrasena } = this.form.getRawValue();
    if (contrasena !== confirmarContrasena) {
      this.errorMessage.set('Las contraseñas no coinciden.');
      return;
    }

    this.submitting.set(true);
    this.auth
      .registro({ nombre, apellido, telefono, usuario, contrasena })
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: (response) => {
          this.successMessage.set(response.mensaje);
          setTimeout(() => void this.router.navigate(['/login']), 900);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(this.errorForStatus(error.status));
        },
      });
  }

  protected togglePassword(): void {
    this.passwordVisible.update((visible) => !visible);
  }

  protected toggleConfirmPassword(): void {
    this.confirmPasswordVisible.update((visible) => !visible);
  }

  private errorForStatus(status: number): string {
    if (status === 409) {
      return 'El nombre de usuario ya está registrado.';
    }
    if (status === 0) {
      return 'No fue posible conectar con el servidor.';
    }
    return 'No fue posible crear la cuenta.';
  }
}
