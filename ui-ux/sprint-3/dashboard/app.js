
document.addEventListener("DOMContentLoaded", function () {
    const toast = document.getElementById("toast");
    const sidebar = document.getElementById("sidebar");
    const menuToggle = document.getElementById("menuToggle");
    const mobileOverlay = document.getElementById("mobileOverlay");

    let toastTimeout;

    // Display a temporary message.
    function showToast(message) {
        if (!toast) return;

        toast.textContent = message;
        toast.classList.add("visible");

        clearTimeout(toastTimeout);
        toastTimeout = setTimeout(function () {
            toast.classList.remove("visible");
        }, 3000);
    }

    // Mobile sidebar.
    function closeSidebar() {
        sidebar.classList.remove("open");
        mobileOverlay.classList.remove("visible");
        menuToggle.setAttribute("aria-expanded", "false");
    }

    menuToggle.addEventListener("click", function () {
        const isOpen = sidebar.classList.toggle("open");
        mobileOverlay.classList.toggle("visible", isOpen);
        menuToggle.setAttribute("aria-expanded", String(isOpen));
    });

    mobileOverlay.addEventListener("click", closeSidebar);

    // Sidebar navigation highlights.
    document.querySelectorAll(".nav-link").forEach(function (link) {
        link.addEventListener("click", function () {
            document.querySelectorAll(".nav-link").forEach(function (item) {
                item.classList.remove("active");
            });

            link.classList.add("active");
            closeSidebar();
        });
    });

    // Save or unsave recommended jobs.
    document.querySelectorAll(".save-job").forEach(function (button) {
        button.addEventListener("click", function () {
            const isSaved = button.classList.toggle("saved");

            button.textContent = isSaved ? "♥" : "♡";
            button.setAttribute("aria-pressed", String(isSaved));

            const jobCard = button.closest(".job-card");
            const jobName = jobCard.dataset.job;

            showToast(
                isSaved
                    ? jobName + " saved to your favourites."
                    : jobName + " removed from your favourites."
            );
        });
    });

    // Simulated job application. No real application is submitted.
    document.querySelectorAll("[data-apply]").forEach(function (button) {
        button.addEventListener("click", function () {
            const jobName = button.dataset.apply;

            showToast(
                "Demo only: " + jobName +
                " application is not submitted to a real employer."
            );
        });
    });

    // Profile completion.
    document.getElementById("completeProfileButton").addEventListener(
        "click",
        function () {
            showToast("Profile editing will be available in a future screen.");
        }
    );

    // Resume upload.
    document.getElementById("uploadResumeButton").addEventListener(
        "click",
        function () {
            showToast("Resume upload screen is part of Sprint 3.");
        }
    );

    // ATS analysis preview.
    document.getElementById("viewAnalysisButton").addEventListener(
        "click",
        function (event) {
            event.preventDefault();
            showToast("ATS analysis details will be shown in the next screen.");
        }
    );

    // Job and application navigation placeholders.
    document.getElementById("viewAllJobs").addEventListener(
        "click",
        function (event) {
            event.preventDefault();
            showToast("You're viewing all sample job recommendations.");
        }
    );

    document.getElementById("viewApplications").addEventListener(
        "click",
        function (event) {
            event.preventDefault();
            showToast("These are your recent sample applications.");
        }
    );

    // Application row details.
    document.querySelectorAll(".row-menu").forEach(function (button) {
        button.addEventListener("click", function () {
            const row = button.closest("tr");
            const position = row.querySelector("td strong").textContent;
            const status = row.querySelector(".status-pill").textContent;

            showToast(position + " — Status: " + status + " (demo data).");
        });
    });

    // Notification and help controls.
    document.getElementById("notificationButton").addEventListener(
        "click",
        function () {
            showToast("You're all caught up! These are sample notifications.");
        }
    );

    document.getElementById("helpButton").addEventListener(
        "click",
        function () {
            showToast("Help centre integration can be added later.");
        }
    );

    document.getElementById("profileButton").addEventListener(
        "click",
        function () {
            showToast("Profile settings are not connected in this prototype.");
        }
    );
});
