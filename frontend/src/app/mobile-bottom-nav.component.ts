import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

@Component({
  imports: [RouterLink, RouterLinkActive],
  selector: 'app-mobile-bottom-nav',
  styleUrl: './mobile-bottom-nav.component.scss',
  templateUrl: './mobile-bottom-nav.component.html',
})
export class MobileBottomNavComponent {}
