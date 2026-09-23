import { CurrencyPipe, DatePipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, of } from 'rxjs';
import { EstadoTransferencia, Transferencia } from './transferencia.model';
import { TransferenciasApiService } from './transferencias-api.service';
import { ConfirmModalComponent } from './confirm-modal.component';

type ConfirmAction = 'reject' | 'restore' | 'delete';

@Component({
  imports: [ConfirmModalComponent, CurrencyPipe, DatePipe, RouterLink],
  selector: 'app-transferencia-detalle',
  styleUrl: './transferencia-detalle.component.scss',
  templateUrl: './transferencia-detalle.component.html',
})
export class TransferenciaDetalleComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(TransferenciasApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly router = inject(Router);

  protected readonly transferencia = signal<Transferencia | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal(false);
  protected readonly errorAccion = signal<string | null>(null);
  protected readonly accionEnCurso = signal<string | null>(null);
  protected readonly modalAbierto = signal(false);
  protected readonly accionModal = signal<ConfirmAction | null>(null);
  protected readonly idTransferencia = Number(
    this.route.snapshot.paramMap.get('id'),
  );
  protected readonly comprobanteUrl = this.api.obtenerUrlComprobante(
    this.idTransferencia,
  );
  protected readonly comprobanteResourceUrl: SafeResourceUrl =
    this.sanitizer.bypassSecurityTrustResourceUrl(this.comprobanteUrl);
  protected anteriorId: number | null = null;
  protected siguienteId: number | null = null;

  protected readonly modalConfig = computed(() => {
    switch (this.accionModal()) {
      case 'reject':
        return {
          title: 'Rechazar transferencia',
          message: '¿Seguro que deseas rechazar esta transferencia?',
          secondaryText: 'La transferencia se moverá a Rechazadas y podrás restaurarla posteriormente.',
          confirmText: 'Rechazar',
          variant: 'danger' as const,
        };
      case 'restore':
        return {
          title: 'Restaurar transferencia',
          message: '¿Deseas restaurar esta transferencia?',
          secondaryText: 'La transferencia volverá al estado Pendiente para poder revisarla nuevamente.',
          confirmText: 'Restaurar',
          variant: 'default' as const,
        };
      case 'delete':
        return {
          title: 'Eliminar definitivamente',
          message: '¿Seguro que deseas eliminar esta transferencia?',
          secondaryText: 'Esta acción no se puede deshacer y el registro será eliminado de la base de datos.',
          confirmText: 'Eliminar definitivamente',
          variant: 'danger' as const,
        };
      default:
        return {
          title: '',
          message: '',
          secondaryText: '',
          confirmText: '',
          variant: 'default' as const,
        };
    }
  });

  constructor() {
    this.api
      .obtenerTransferencias()
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        catchError(() => {
          this.error.set(true);
          this.cargando.set(false);
          return of(null);
        }),
      )
      .subscribe((respuesta) => {
        if (!respuesta) {
          return;
        }
        const registros = respuesta.transferencias ?? [];
        const indice = registros.findIndex(
          (registro) => registro.id_transferencia === this.idTransferencia,
        );
        if (indice < 0) {
          this.error.set(true);
        } else {
          this.transferencia.set(registros[indice]);
          this.anteriorId = registros[indice - 1]?.id_transferencia ?? null;
          this.siguienteId = registros[indice + 1]?.id_transferencia ?? null;
        }
        this.cargando.set(false);
      });
  }

  protected estadoClase(estado: string | null): string {
    return (estado ?? 'PENDIENTE').toLowerCase().replace('_', '-');
  }

  protected formatearEstado(estado: string | null): string {
    return (estado ?? 'PENDIENTE').replace('_', ' ');
  }

  protected iniciales(chat: string | null): string {
    return (chat ?? '—')
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((palabra) => palabra[0].toUpperCase())
      .join('') || '—';
  }

  protected esPdf(transferencia: Transferencia): boolean {
    return transferencia.tipo_archivo === 'PDF';
  }

  protected valor(valor: string | number | null): string | number {
    return valor === null || valor === '' ? '—' : valor;
  }

  protected rechazar(): void {
    if (
      this.accionEnCurso() !== null
      || this.transferencia()?.estado !== 'PENDIENTE'
    ) {
      return;
    }

    this.abrirModal('reject');
  }

  protected restaurar(): void {
    if (
      this.accionEnCurso() !== null
      || this.transferencia()?.estado !== 'RECHAZADA'
    ) {
      return;
    }

    this.abrirModal('restore');
  }

  protected eliminarDefinitivamente(): void {
    if (
      this.accionEnCurso() !== null
      || this.transferencia()?.estado !== 'RECHAZADA'
    ) {
      return;
    }

    this.abrirModal('delete');
  }

  protected cancelarModal(): void {
    if (this.accionEnCurso() !== null) {
      return;
    }
    this.modalAbierto.set(false);
    this.accionModal.set(null);
    this.errorAccion.set(null);
  }

  protected confirmarModal(): void {
    if (this.accionEnCurso() !== null) {
      return;
    }

    switch (this.accionModal()) {
      case 'reject':
        this.cambiarEstado('RECHAZADA');
        break;
      case 'restore':
        this.cambiarEstado('PENDIENTE');
        break;
      case 'delete':
        this.eliminarConfirmado();
        break;
    }
  }

  private abrirModal(accion: ConfirmAction): void {
    this.errorAccion.set(null);
    this.accionModal.set(accion);
    this.modalAbierto.set(true);
  }

  private eliminarConfirmado(): void {
    this.accionEnCurso.set('eliminar');
    this.errorAccion.set(null);
    this.api.eliminarTransferencia(this.idTransferencia).subscribe({
      next: () => {
        this.modalAbierto.set(false);
        this.router.navigateByUrl('/transferencias');
      },
      error: () => {
        this.accionEnCurso.set(null);
        this.errorAccion.set('No fue posible eliminar la transferencia.');
      },
    });
  }

  private cambiarEstado(estado: 'PENDIENTE' | 'RECHAZADA'): void {
    this.accionEnCurso.set(estado === 'RECHAZADA' ? 'rechazar' : 'restaurar');
    this.errorAccion.set(null);
    this.api.cambiarEstado(this.idTransferencia, estado).subscribe({
      next: () => {
        this.modalAbierto.set(false);
        this.router.navigateByUrl('/transferencias');
      },
      error: () => {
        this.accionEnCurso.set(null);
        this.errorAccion.set('No fue posible cambiar el estado.');
      },
    });
  }
}
