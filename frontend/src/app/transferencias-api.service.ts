import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { TransferenciasResponse } from './transferencia.model';

export type EstadoGestionTransferencia = 'PENDIENTE' | 'RECHAZADA';

@Injectable({ providedIn: 'root' })
export class TransferenciasApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://127.0.0.1:5000/api/transferencias';

  obtenerTransferencias(): Observable<TransferenciasResponse> {
    return this.http.get<TransferenciasResponse>(this.apiUrl);
  }

  obtenerUrlComprobante(idTransferencia: number): string {
    return `${this.apiUrl}/${idTransferencia}/comprobante`;
  }

  cambiarEstado(
    idTransferencia: number,
    estado: EstadoGestionTransferencia,
  ): Observable<unknown> {
    return this.http.patch(`${this.apiUrl}/${idTransferencia}/estado`, {
      estado,
    });
  }

  eliminarTransferencia(idTransferencia: number): Observable<unknown> {
    return this.http.delete(`${this.apiUrl}/${idTransferencia}`);
  }
}
