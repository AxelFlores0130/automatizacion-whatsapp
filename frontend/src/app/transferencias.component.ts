import { CurrencyPipe, DatePipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, of } from 'rxjs';
import {
  EstadoTransferencia,
  Transferencia,
} from './transferencia.model';
import { TransferenciasApiService } from './transferencias-api.service';
import { AuthService } from './auth.service';

@Component({
  imports: [CurrencyPipe, DatePipe, RouterLink],
  selector: 'app-transferencias',
  styleUrl: './transferencias.component.scss',
  templateUrl: './transferencias.component.html',
})
export class TransferenciasComponent {
  private readonly api = inject(TransferenciasApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);
  protected readonly auth = inject(AuthService);
  protected readonly usuarioActual = this.auth.getCurrentUser();
  private pollingId: ReturnType<typeof setInterval> | undefined;

  protected readonly transferencias = signal<Transferencia[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal(false);
  protected readonly busqueda = signal('');
  protected readonly estadoSeleccionado = signal('TODOS');
  protected readonly menuEstadosAbierto = signal(false);
  protected readonly tipoSeleccionado = signal('TODOS');
  protected readonly estados = [
    'TODOS',
    'PENDIENTE',
    'EN_REVISION',
    'VALIDADA',
    'RECHAZADA',
    'REGISTRADA',
  ];
  protected readonly tipos = ['TODOS', 'IMAGEN', 'PDF'];

  protected readonly resumen = computed(() => {
    const registros = this.transferencias();
    return {
      total: registros.length,
      pendientes: this.contarEstado(registros, 'PENDIENTE'),
      enRevision: this.contarEstado(registros, 'EN_REVISION'),
      validadas: this.contarEstado(registros, 'VALIDADA'),
      rechazadas: this.contarEstado(registros, 'RECHAZADA'),
      registradas: this.contarEstado(registros, 'REGISTRADA'),
    };
  });

  protected readonly transferenciasFiltradas = computed(() => {
    const termino = this.busqueda().trim().toLowerCase();
    const estado = this.estadoSeleccionado();
    const tipo = this.tipoSeleccionado();

    return this.transferencias().filter((transferencia) => {
      const coincideEstado =
        estado === 'TODOS' || (transferencia.estado ?? '') === estado;
      const coincideTipo =
        tipo === 'TODOS' || (transferencia.tipo_archivo ?? '') === tipo;
      const texto = [
        transferencia.chat,
        transferencia.destinatario,
        transferencia.folio,
        transferencia.monto?.toString(),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      return coincideEstado && coincideTipo && (!termino || texto.includes(termino));
    });
  });

  constructor() {
    this.cargarTransferencias();
    this.pollingId = setInterval(() => this.cargarTransferencias(true), 5000);
    this.destroyRef.onDestroy(() => {
      if (this.pollingId !== undefined) {
        clearInterval(this.pollingId);
      }
    });
  }

  protected seleccionarEstado(estado: string): void {
    this.estadoSeleccionado.set(estado);
    this.menuEstadosAbierto.set(false);
  }

  protected alternarMenuEstados(): void {
    this.menuEstadosAbierto.update((abierto) => !abierto);
  }

  protected cerrarMenuEstados(): void {
    this.menuEstadosAbierto.set(false);
  }

  protected cerrarSesion(): void {
    this.auth.logout();
    void this.router.navigate(['/login']);
  }

  protected abrirTransferencia(event: Event, id: number): void {
    if (event instanceof KeyboardEvent && event.key === ' ') {
      event.preventDefault();
    }
    void this.router.navigate(['/transferencias', id]);
  }

  protected actualizarBusqueda(event: Event): void {
    this.busqueda.set((event.target as HTMLInputElement).value);
  }

  protected actualizarTipo(event: Event): void {
    this.tipoSeleccionado.set((event.target as HTMLSelectElement).value);
  }

  protected limpiarFiltros(): void {
    this.busqueda.set('');
    this.tipoSeleccionado.set('TODOS');
    this.estadoSeleccionado.set('TODOS');
  }

  protected iniciales(chat: string | null): string {
    const palabras = (chat ?? '—').trim().split(/\s+/).filter(Boolean);
    if (palabras.length === 0) {
      return '—';
    }
    return palabras
      .slice(0, 2)
      .map((palabra) => palabra[0].toUpperCase())
      .join('');
  }

  protected estadoClase(estado: string | null): string {
    return (estado ?? 'PENDIENTE').toLowerCase().replace('_', '-');
  }

  protected formatearEstado(estado: string | null): string {
    return (estado ?? 'PENDIENTE').replace('_', ' ');
  }

  protected contarEstadoVisible(estado: string): number {
    return this.contarEstado(this.transferencias(), estado);
  }

  private cargarTransferencias(esRefresco = false): void {
    if (!esRefresco) {
      this.cargando.set(true);
    }

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
        this.transferencias.set(respuesta.transferencias ?? []);
        this.error.set(false);
        this.cargando.set(false);
      });
  }

  private contarEstado(
    transferencias: Transferencia[],
    estado: EstadoTransferencia,
  ): number {
    return transferencias.filter((transferencia) => transferencia.estado === estado).length;
  }
}
