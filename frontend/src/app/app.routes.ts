import { Routes } from '@angular/router';
import { authGuard, publicAuthGuard } from './auth.guard';
import { LoginComponent } from './login.component';
import { RegistroComponent } from './registro.component';
import { TransferenciaDetalleComponent } from './transferencia-detalle.component';
import { TransferenciasComponent } from './transferencias.component';

export const routes: Routes = [
	{ path: '', pathMatch: 'full', redirectTo: 'transferencias' },
	{ path: 'login', component: LoginComponent, canActivate: [publicAuthGuard] },
	{ path: 'registro', component: RegistroComponent, canActivate: [publicAuthGuard] },
	{ path: 'transferencias', component: TransferenciasComponent, canActivate: [authGuard] },
	{ path: 'transferencias/:id', component: TransferenciaDetalleComponent, canActivate: [authGuard] },
	{ path: '**', redirectTo: 'transferencias' },
];
