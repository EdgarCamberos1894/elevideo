import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useAuth } from '@/context/AuthContext';
import { useTheme } from '@/context/ThemeContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardFooter } from '@/components/ui/card';
import { EleVideoLogo } from '@/components/EleVideoLogo';
import { toast } from 'sonner';
import { Film, Loader2, Eye, EyeOff, Moon, Sun, Sparkles, ArrowRight, MailCheck } from 'lucide-react';

const loginSchema = z.object({
  email: z.string().email('Introduce un correo electrónico válido'),
  password: z.string().min(8, 'La contraseña debe tener al menos 8 caracteres'),
});

const demoCredentials = {
  email: 'demo@elevideo.app',
  password: 'Demo123!',
};

export function LoginPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [verificationRequired, setVerificationRequired] = useState(false);
  const { login } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  const registrationSuccess = location.state?.registrationSuccess === true;
  const verificationEmail = location.state?.verificationEmail || '';

  const form = useForm({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: verificationEmail,
      password: '',
    },
  });

  const onSubmit = async (data) => {
    setIsLoading(true);
    setVerificationRequired(false);
    try {
      await login(data);
      toast.success('¡Bienvenido de vuelta!');
      navigate('/dashboard');
    } catch (error) {
      const message = error.response?.data?.message || 'Error al iniciar sesión';
      const isUnverifiedEmail = error.response?.status === 403 && /verificar.*email|email.*verificar/i.test(message);

      if (isUnverifiedEmail) {
        setVerificationRequired(true);
        toast.error(`${message} Si no encuentras el correo, revisa Spam o Correo no deseado.`);
      } else {
        toast.error(message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleDemoLogin = async () => {
    form.reset(demoCredentials);
    await onSubmit(demoCredentials);
  };

  return (
    <div className="min-h-screen auth-bg relative overflow-hidden">
      {/* Theme Toggle */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-4 right-4 z-50 bg-background/50 backdrop-blur-sm"
        onClick={toggleTheme}
        aria-label={theme === 'light' ? 'Usar tema oscuro' : 'Usar tema claro'}
        title={theme === 'light' ? 'Tema oscuro' : 'Tema claro'}
        data-testid="theme-toggle"
      >
        {theme === 'light' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5 text-yellow-400" />}
      </Button>

      {/* Content */}
      <div className="relative z-10 min-h-screen flex items-center justify-center p-4 py-10">
        <div className="w-full max-w-md space-y-6">
          {/* Logo */}
          <div className="text-center space-y-4">
            <EleVideoLogo
              compact
              className="justify-center"
              markClassName="h-20 w-20"
            />
            <div>
              <h1 className="font-outfit text-3xl font-bold tracking-tight">
                Bienvenido a <span className="gradient-text">Elevideo</span>
              </h1>
              <p className="text-muted-foreground mt-2">
                Convierte tus videos horizontales a verticales con IA
              </p>
            </div>
          </div>

          {(registrationSuccess || verificationRequired) && (
            <div
              className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm"
              role="status"
              data-testid="email-verification-notice"
            >
              <div className="flex items-start gap-3">
                <MailCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <div className="space-y-1">
                  <p className="font-semibold text-foreground">
                    {registrationSuccess ? 'Cuenta creada. Verifica tu correo antes de iniciar sesión.' : 'Tu correo aún no está verificado.'}
                  </p>
                  <p className="text-muted-foreground">
                    {verificationEmail
                      ? <>Enviamos el enlace de verificación a <span className="font-medium text-foreground">{verificationEmail}</span>. </>
                      : null}
                    Si no lo encuentras en tu bandeja de entrada, revisa también <strong>Spam</strong> o <strong>Correo no deseado</strong>.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Card */}
          <Card className="border-border/50 bg-card/80 backdrop-blur-xl shadow-2xl">
            <form onSubmit={form.handleSubmit(onSubmit)}>
              <CardContent className="space-y-5 pt-6">
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-sm font-medium">
                    Correo electrónico
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    placeholder="tu@email.com"
                    className="h-12 bg-background/50 border-border/50 focus:border-accent"
                    data-testid="login-email-input"
                    tabIndex={1}
                    autoFocus
                    {...form.register('email')}
                  />
                  {form.formState.errors.email && (
                    <p className="text-sm text-destructive">{form.formState.errors.email.message}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password" className="text-sm font-medium">
                    Contraseña
                  </Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      placeholder="••••••••"
                      className="h-12 bg-background/50 border-border/50 focus:border-accent pr-12"
                      data-testid="login-password-input"
                      {...form.register('password')}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                      title={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4 text-muted-foreground" /> : <Eye className="h-4 w-4 text-muted-foreground" />}
                    </Button>
                  </div>
                  {form.formState.errors.password && (
                    <p className="text-sm text-destructive">{form.formState.errors.password.message}</p>
                  )}
                </div>
                <div className="flex justify-end">
                  <Link
                    to="/forgot-password"
                    className="text-sm text-muted-foreground hover:text-accent transition-colors"
                  >
                    ¿Olvidaste tu contraseña?
                  </Link>
                </div>
              </CardContent>
              <CardFooter className="flex flex-col gap-4 pb-6">
                <Button
                  type="submit"
                  variant="gradient"
                  className="h-12 w-full font-medium"
                  disabled={isLoading}
                  data-testid="login-submit-button"
                >
                  {isLoading ? (
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-5 w-5" />
                  )}
                  Iniciar sesión
                </Button>
                <p className="text-sm text-muted-foreground text-center">
                  ¿No tienes cuenta?{' '}
                  <Link to="/register" className="text-accent hover:underline font-medium">
                    Regístrate gratis
                  </Link>
                </p>
                <section className="w-full border-t border-border/60 pt-4" aria-labelledby="elevideo-demo-title">
                  <div className="space-y-1 text-left">
                    <p id="elevideo-demo-title" className="text-sm font-semibold">
                      Acceso de demostración
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {demoCredentials.email} · Contraseña: {demoCredentials.password}
                    </p>
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      Los datos de esta cuenta se restablecen periódicamente.
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="brand"
                    className="mt-3 w-full"
                    onClick={handleDemoLogin}
                    disabled={isLoading}
                    data-testid="load-demo-credentials"
                  >
                    {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ArrowRight className="mr-2 h-4 w-4" />}
                    Entrar a la demostración
                  </Button>
                </section>
              </CardFooter>
            </form>
          </Card>

          {/* Features */}
          <div className="grid grid-cols-3 gap-4 text-center text-xs text-muted-foreground">
            <div className="space-y-1">
              <div className="w-8 h-8 mx-auto rounded-lg bg-blue-500/10 flex items-center justify-center">
                <Film className="h-4 w-4 text-blue-500" />
              </div>
              <p>Encuadre inteligente</p>
            </div>
            <div className="space-y-1">
              <div className="w-8 h-8 mx-auto rounded-lg bg-purple-500/10 flex items-center justify-center">
                <Sparkles className="h-4 w-4 text-purple-500" />
              </div>
              <p>IA automática</p>
            </div>
            <div className="space-y-1">
              <div className="w-8 h-8 mx-auto rounded-lg bg-pink-500/10 flex items-center justify-center">
                <ArrowRight className="h-4 w-4 text-pink-500" />
              </div>
              <p>Clips automáticos</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
