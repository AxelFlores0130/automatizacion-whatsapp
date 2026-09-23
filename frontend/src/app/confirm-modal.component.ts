import {
  Component,
  ElementRef,
  OnDestroy,
  output,
  input,
} from '@angular/core';

export type ConfirmModalVariant = 'default' | 'danger';

@Component({
  selector: 'app-confirm-modal',
  templateUrl: './confirm-modal.component.html',
  styleUrl: './confirm-modal.component.scss',
})
export class ConfirmModalComponent implements OnDestroy {
  readonly title = input.required<string>();
  readonly message = input.required<string>();
  readonly secondaryText = input<string>('');
  readonly confirmText = input.required<string>();
  readonly variant = input<ConfirmModalVariant>('default');
  readonly loading = input(false);
  readonly errorMessage = input<string | null>(null);
  readonly confirm = output<void>();
  readonly cancel = output<void>();

  private readonly previousBodyOverflow: string;
  private readonly keydownListener = (event: KeyboardEvent): void => {
    if (event.key === 'Escape' && !this.loading()) {
      this.cancel.emit();
    }
  };

  constructor(private readonly elementRef: ElementRef<HTMLElement>) {
    this.previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', this.keydownListener);
    queueMicrotask(() => {
      this.elementRef.nativeElement
        .querySelector<HTMLButtonElement>('.cancel-button')
        ?.focus();
    });
  }

  ngOnDestroy(): void {
    document.body.style.overflow = this.previousBodyOverflow;
    document.removeEventListener('keydown', this.keydownListener);
  }

  protected closeFromBackdrop(event: MouseEvent): void {
    if (!this.loading() && event.target === event.currentTarget) {
      this.cancel.emit();
    }
  }
}
