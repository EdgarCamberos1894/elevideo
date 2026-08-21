import { useEffect, useMemo, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';

const DISPLAY_DEFAULTS = {
  maxCameraSpeed: 35,
  applySharpening: true,
  useRuleOfThirds: true,
  edgePadding: 15,
};

export function AdvancedProcessingOptions({ backgroundMode, onChange }) {
  const [values, setValues] = useState(DISPLAY_DEFAULTS);
  const [overrides, setOverrides] = useState({});
  const usesSmartCrop = backgroundMode === 'smart_crop';

  const effectiveOverrides = useMemo(() => {
    if (usesSmartCrop) return overrides;

    return overrides.applySharpening === undefined
      ? {}
      : { applySharpening: overrides.applySharpening };
  }, [overrides, usesSmartCrop]);

  useEffect(() => {
    onChange(effectiveOverrides);
  }, [effectiveOverrides, onChange]);

  const updateOption = (key, value) => {
    setValues((current) => ({ ...current, [key]: value }));
    setOverrides((current) => ({ ...current, [key]: value }));
  };

  const resetToPreset = () => {
    setValues(DISPLAY_DEFAULTS);
    setOverrides({});
  };

  const hasOverrides = Object.keys(effectiveOverrides).length > 0;

  return (
    <div className="space-y-4 p-4 rounded-xl bg-muted/30 border border-dashed border-border">
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-medium">Ajustes avanzados</p>
          {hasOverrides && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={resetToPreset}
              className="h-8 px-2 text-xs"
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              Usar preset
            </Button>
          )}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Abrir este panel no cambia el procesamiento. Solo los controles que modifiques reemplazan valores del preset actual.
        </p>
      </div>

      {usesSmartCrop ? (
        <>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <div>
                <Label className="text-xs">Velocidad de seguimiento</Label>
                <p className="text-xs leading-relaxed text-muted-foreground">Menor = movimiento más calmado; mayor = sigue desplazamientos rápidos.</p>
              </div>
              <span className="shrink-0 rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                {values.maxCameraSpeed} px/frame
              </span>
            </div>
            <Slider
              value={[values.maxCameraSpeed]}
              onValueChange={([value]) => updateOption('maxCameraSpeed', value)}
              min={10}
              max={100}
              step={5}
              data-testid="max-camera-speed-slider"
            />
          </div>

          <div className="flex items-center justify-between gap-4 rounded-lg border bg-background/50 p-3">
            <div>
              <Label className="text-xs">Regla de tercios</Label>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">Desplaza la composición para evitar centrar siempre el rostro.</p>
            </div>
            <Switch
              checked={values.useRuleOfThirds}
              onCheckedChange={(checked) => updateOption('useRuleOfThirds', checked)}
              data-testid="rule-of-thirds-toggle"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <div>
                <Label className="text-xs">Margen lateral</Label>
                <p className="text-xs leading-relaxed text-muted-foreground">Evita que el recorte se acerque demasiado a los bordes del video.</p>
              </div>
              <span className="shrink-0 rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                {values.edgePadding}px
              </span>
            </div>
            <Slider
              value={[values.edgePadding]}
              onValueChange={([value]) => updateOption('edgePadding', value)}
              min={0}
              max={50}
              step={5}
              data-testid="edge-padding-slider"
            />
          </div>
        </>
      ) : (
        <p className="rounded-lg border bg-background/50 p-3 text-xs leading-relaxed text-muted-foreground">
          El fondo seleccionado conserva el video completo, por lo que los ajustes de seguimiento facial no aplican.
        </p>
      )}

      <div className="flex items-center justify-between gap-4 rounded-lg border bg-background/50 p-3">
        <div>
          <Label className="text-xs">Nitidez adicional</Label>
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">Aplica un filtro de enfoque al resultado final después de adaptar el video a 9:16.</p>
        </div>
        <Switch
          checked={values.applySharpening}
          onCheckedChange={(checked) => updateOption('applySharpening', checked)}
          data-testid="sharpening-toggle"
        />
      </div>
    </div>
  );
}
