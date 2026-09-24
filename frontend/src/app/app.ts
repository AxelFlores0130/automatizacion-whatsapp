import { Component, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { AuthService } from './auth.service';
import { MobileBottomNavComponent } from './mobile-bottom-nav.component';

@Component({
  imports: [MobileBottomNavComponent, RouterOutlet],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  protected readonly mostrarBottomNav = signal(
    this.debeMostrarBottomNav(window.location.pathname),
  );

  constructor() {
    this.router.events
      .pipe(filter((event) => event instanceof NavigationEnd))
      .subscribe(() => this.mostrarBottomNav.set(this.debeMostrarBottomNav()));
  }

  private debeMostrarBottomNav(ruta = this.router.url): boolean {
    return this.auth.isAuthenticated() && ruta !== '/login' && ruta !== '/registro';
  }
}
