package com.elevideo.backend.auth.internal;

import com.elevideo.backend.auth.api.dto.LoginRequest;
import com.elevideo.backend.auth.api.dto.RegisterRequest;
import com.elevideo.backend.auth.api.dto.VerifyEmailRequest;
import com.elevideo.backend.shared.event.DomainEventPublisher;
import com.elevideo.backend.shared.security.JwtService;
import com.elevideo.backend.shared.security.TokenPurpose;
import com.elevideo.backend.user.api.UserService;
import com.elevideo.backend.user.api.dto.UserResponse;
import com.elevideo.backend.user.internal.UserMapper;
import com.elevideo.backend.user.internal.UserRepository;
import com.elevideo.backend.user.internal.model.AccountStatus;
import com.elevideo.backend.user.internal.model.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.BDDMockito.*;

@ExtendWith(MockitoExtension.class)
@DisplayName("AuthServiceImpl")
class AuthServiceImplTest {

    @Mock UserRepository         userRepository;
    @Mock UserMapper             userMapper;
    @Mock UserService            userService;
    @Mock AuthenticationManager  authenticationManager;
    @Mock PasswordEncoder        passwordEncoder;
    @Mock JwtService             jwtService;
    @Mock TokenBlacklistService  blacklistService;
    @Mock DomainEventPublisher   eventPublisher;

    @InjectMocks AuthServiceImpl authService;

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(authService, "frontendBaseUrl",     "http://localhost:3000");
        ReflectionTestUtils.setField(authService, "verifyEmailPath",     "/verify-email");
        ReflectionTestUtils.setField(authService, "resetPasswordPath",   "/reset-password");
    }

    // ----------------------------------------------------------------
    // register
    // ----------------------------------------------------------------

    @Nested
    @DisplayName("register()")
    class Register {

        @Test
        @DisplayName("should save user and publish UserRegisteredEvent")
        void shouldRegisterUserAndPublishEvent() {
            RegisterRequest request = new RegisterRequest(
                    "Juan", "Pérez", "juan@example.com", "P@ssw0rd!"
            );
            User savedUser = buildUser();

            given(userRepository.existsByEmail(request.email())).willReturn(false);
            given(passwordEncoder.encode(request.password())).willReturn("hashed");
            given(userMapper.toUser(eq(request), eq("hashed"))).willReturn(savedUser);
            given(userMapper.toUserRes(savedUser)).willReturn(buildUserResponse(savedUser));
            given(jwtService.generateUserToken(any(), eq(TokenPurpose.EMAIL_VERIFICATION)))
                    .willReturn("verification-token");

            UserResponse result = authService.register(request);

            then(userRepository).should().save(savedUser);
            then(eventPublisher).should().publish(any());
            assertThat(result.email()).isEqualTo("juan@example.com");
        }

        @Test
        @DisplayName("should throw UserAlreadyExistsException when email is taken")
        void shouldThrowWhenEmailExists() {
            RegisterRequest request = new RegisterRequest(
                    "Juan", "Pérez", "taken@example.com", "P@ssw0rd!"
            );
            given(userRepository.existsByEmail(request.email())).willReturn(true);

            assertThatThrownBy(() -> authService.register(request))
                    .isInstanceOf(UserAlreadyExistsException.class);

            then(userRepository).should(never()).save(any());
            then(eventPublisher).should(never()).publish(any());
        }
    }

    // ----------------------------------------------------------------
    // login
    // ----------------------------------------------------------------

    @Nested
    @DisplayName("login()")
    class Login {

        @Test
        @DisplayName("should return JWT token on valid credentials")
        void shouldReturnTokenOnValidCredentials() {
            LoginRequest request = new LoginRequest("juan@example.com", "P@ssw0rd!");
            User user = buildActiveUser();

            given(authenticationManager.authenticate(any(UsernamePasswordAuthenticationToken.class)))
                    .willReturn(mock(org.springframework.security.core.Authentication.class));
            given(userRepository.findByEmail(request.email())).willReturn(Optional.of(user));
            given(jwtService.generateUserToken(any(), eq(TokenPurpose.AUTHENTICATION)))
                    .willReturn("jwt-token");

            var result = authService.login(request);

            assertThat(result.token()).isEqualTo("jwt-token");
        }

        @Test
        @DisplayName("should throw BadCredentialsException on invalid credentials")
        void shouldThrowOnInvalidCredentials() {
            LoginRequest request = new LoginRequest("juan@example.com", "wrong");

            given(authenticationManager.authenticate(any()))
                    .willThrow(new BadCredentialsException("Invalid credentials"));

            assertThatThrownBy(() -> authService.login(request))
                    .isInstanceOf(BadCredentialsException.class);
        }
    }

    // ----------------------------------------------------------------
    // forgotPassword
    // ----------------------------------------------------------------

    @Nested
    @DisplayName("forgotPassword()")
    class ForgotPassword {

        @Test
        @DisplayName("should publish event when email exists")
        void shouldPublishEventWhenEmailExists() {
            User user = buildActiveUser();
            given(userRepository.findByEmail("juan@example.com")).willReturn(Optional.of(user));
            given(jwtService.generateUserToken(any(), eq(TokenPurpose.PASSWORD_RESET)))
                    .willReturn("reset-token");

            authService.forgotPassword(new com.elevideo.backend.auth.api.dto.ForgotPasswordRequest("juan@example.com"));

            then(eventPublisher).should().publish(any());
        }

        @Test
        @DisplayName("should NOT reveal if email does not exist (security by design)")
        void shouldNotRevealWhenEmailDoesNotExist() {
            given(userRepository.findByEmail("unknown@example.com")).willReturn(Optional.empty());

            assertThatNoException().isThrownBy(() ->
                    authService.forgotPassword(new com.elevideo.backend.auth.api.dto.ForgotPasswordRequest("unknown@example.com"))
            );

            then(eventPublisher).should(never()).publish(any());
        }
    }

    // ----------------------------------------------------------------
    // Helpers
    // ----------------------------------------------------------------

    private User buildUser() {
        User u = new User();
        u.setId(UUID.randomUUID());
        u.setEmail("juan@example.com");
        u.setFirstName("Juan");
        u.setLastName("Pérez");
        u.setAccountStatus(AccountStatus.PENDING_VERIFICATION);
        return u;
    }

    private User buildActiveUser() {
        User u = buildUser();
        u.setAccountStatus(AccountStatus.ACTIVE);
        u.setEmailVerified(true);
        return u;
    }

    private UserResponse buildUserResponse(User u) {
        return new UserResponse(u.getId(), u.getFirstName(), u.getLastName(),
                u.getEmail(), false, null);
    }
}
