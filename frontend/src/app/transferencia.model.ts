export type EstadoTransferencia =
  | 'PENDIENTE'
  | 'EN_REVISION'
  | 'VALIDADA'
  | 'RECHAZADA'
  | 'REGISTRADA'
  | string;

export interface Transferencia {
  id_transferencia: number;
  mensaje_whatsapp_id: string | null;
  chat: string | null;
  tipo_archivo: 'IMAGEN' | 'PDF' | string | null;
  monto: number | null;
  destinatario: string | null;
  cuenta_destino: string | null;
  cuenta_origen: string | null;
  comision: number | null;
  concepto: string | null;
  tipo_operacion: string | null;
  folio: string | null;
  fecha_transferencia: string | null;
  hora_transferencia: string | null;
  estado: EstadoTransferencia | null;
  id_cliente_dorian: number | null;
  id_pago_dorian: number | null;
  fecha_deteccion: string | null;
  fecha_validacion: string | null;
  fecha_registro_dorian: string | null;
  archivo_comprobante: string | null;
}

export interface TransferenciasResponse {
  success: boolean;
  total: number;
  transferencias: Transferencia[];
}
