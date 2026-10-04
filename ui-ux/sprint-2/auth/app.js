const signupForm = document.getElementById("signupForm");
const signinForm = document.getElementById("signinForm");

// Sign Up
if (signupForm) {
    signupForm.addEventListener("submit", function (event) {
        event.preventDefault();

        const password = document.getElementById("password").value;
        const confirmPassword =
            document.getElementById("confirmPassword").value;

        if (password !== confirmPassword) {
            alert("Passwords do not match.");
            return;
        }

        alert("Account created successfully!");
    });
}

// Sign In
if (signinForm) {
    signinForm.addEventListener("submit", function (event) {
        event.preventDefault();

        const email = document.getElementById("email").value.trim();
        const password = document.getElementById("password").value;

        if (!email || !password) {
            alert("Please enter your email and password.");
            return;
        }

        alert("Sign in successful!");
    });
}

// Google button
const googleButton = document.querySelector(".google-button, .google-btn");

if (googleButton) {
    googleButton.addEventListener("click", function () {
        alert("Google sign-in is currently unavailable.");
    });
}

// Forgot password
const forgotPassword = document.querySelector(".forgot-password");

if (forgotPassword) {
    forgotPassword.addEventListener("click", function (event) {
        event.preventDefault();
        alert("Password recovery will be available soon.");
    });
}