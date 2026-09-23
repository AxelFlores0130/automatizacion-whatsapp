import { Routes } from '@angular/router';
import { TransferenciaDetalleComponent } from './transferencia-detalle.component';
import { TransferenciasComponent } from './transferencias.component';

export const routes: Routes = [
	{ path: '', pathMatch: 'full', redirectTo: 'transferencias' },
	{ path: 'transferencias', component: TransferenciasComponent },
	{ path: 'transferencias/:id', component: TransferenciaDetalleComponent },
	{ path: '**', redirectTo: 'transferencias' },
];
