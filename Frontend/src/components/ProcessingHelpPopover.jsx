import { Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

const MODE_HELP = {
  vertical: {
    title: 'Video completo',
    description: 'Procesa el video de principio a fin y lo adapta a formato vertical 9:16 usando la plataforma, calidad, fondo y opciones avanzadas que elijas. No recorta la duración.',
  },
  short_auto: {
    title: 'Short automático',
    description: 'Analiza rostros, audio, movimiento, silencios y cambios de escena para elegir un tramo con buen inicio y un cierre natural. Con duración Automática decide también cuánto debe durar; Aproximada puede variar unos segundos y Exacta respeta el tiempo indicado.',
  },
  short_manual: {
    title: 'Short manual',
    description: 'Tú decides exactamente dónde empieza el clip y cuánto dura. EleVideo recorta ese intervalo y aplica después el mismo procesamiento vertical que al resto de modos.',
  },
};

function BackgroundDiagram({ type }) {
  if (type === 'smart_crop') {
    return (
      <div className="relative h-24 w-14 shrink-0 overflow-hidden rounded-md border bg-muted">
        <div className="absolute inset-y-0 -left-5 w-24 bg-gradient-to-r from-slate-700 via-slate-500 to-slate-700" />
        <div className="absolute left-1/2 top-7 h-6 w-6 -translate-x-1/2 rounded-full border-2 border-white/90 bg-slate-300/80" />
        <div className="absolute inset-y-2 left-1/2 w-px -translate-x-1/2 border-l border-dashed border-white/80" />
      </div>
    );
  }

  if (type === 'blurred') {
    return (
      <div className="relative h-24 w-14 shrink-0 overflow-hidden rounded-md border bg-slate-700">
        <div className="absolute inset-0 scale-125 bg-gradient-to-b from-indigo-400/70 via-slate-500 to-purple-500/70 blur-md" />
        <div className="absolute left-1/2 top-1/2 h-9 w-12 -translate-x-1/2 -translate-y-1/2 rounded-sm border border-white/70 bg-slate-800/80" />
      </div>
    );
  }

  return (
    <div className="relative h-24 w-14 shrink-0 overflow-hidden rounded-md border bg-black">
      <div className="absolute left-1/2 top-1/2 h-9 w-12 -translate-x-1/2 -translate-y-1/2 rounded-sm border border-white/40 bg-slate-700" />
    </div>
  );
}

function QualityHelp() {
  return (
    <div className="space-y-3">
      <div>
        <p className="font-semibold">Calidad de procesamiento</p>
        <p className="mt-1 text-xs text-muted-foreground">Cambia cuánto análisis y trabajo de codificación dedica EleVideo al resultado.</p>
      </div>
      <div className="space-y-2 text-xs">
        <div><span className="font-medium">Rápido:</span> prioriza velocidad y analiza menos frames.</div>
        <div><span className="font-medium">Normal:</span> equilibrio recomendado entre tiempo y calidad.</div>
        <div><span className="font-medium">Alta:</span> analiza con mayor frecuencia y usa procesamiento multipass; puede tardar más.</div>
      </div>
    </div>
  );
}

function BackgroundHelp() {
  const items = [
    {
      type: 'smart_crop',
      title: 'Recorte inteligente',
      text: 'Recorta a 9:16 y mueve el encuadre para seguir el rostro principal. Si no logra detectar rostros, usa el video completo como alternativa.',
    },
    {
      type: 'blurred',
      title: 'Fondo difuminado',
      text: 'Mantiene todo el video visible y rellena el espacio vertical con una copia ampliada y desenfocada del propio video.',
    },
    {
      type: 'black',
      title: 'Barras negras',
      text: 'Mantiene todo el video visible y completa el espacio sobrante del formato 9:16 con fondo negro.',
    },
  ];

  return (
    <div className="space-y-3">
      <div>
        <p className="font-semibold">Cómo se adapta el fondo</p>
        <p className="mt-1 text-xs text-muted-foreground">La miniatura es ilustrativa; el resultado conserva la proporción vertical 9:16.</p>
      </div>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.type} className="flex gap-3 rounded-lg border bg-muted/20 p-2.5">
            <BackgroundDiagram type={item.type} />
            <div className="min-w-0">
              <p className="text-sm font-medium">{item.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ProcessingHelpPopover({ topic, className = '' }) {
  const mode = MODE_HELP[topic];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={`h-7 w-7 rounded-full text-muted-foreground hover:text-foreground ${className}`}
          aria-label="Ver explicación"
        >
          <Info className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className={topic === 'backgrounds' ? 'w-80 sm:w-96' : 'w-72'}>
        {mode ? (
          <div className="space-y-2">
            <p className="font-semibold">{mode.title}</p>
            <p className="text-sm leading-relaxed text-muted-foreground">{mode.description}</p>
          </div>
        ) : topic === 'quality' ? (
          <QualityHelp />
        ) : (
          <BackgroundHelp />
        )}
      </PopoverContent>
    </Popover>
  );
}
