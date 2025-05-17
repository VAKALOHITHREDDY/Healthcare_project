<canvas id="attendanceChart" width="400" height="200"></canvas>
<script>
const ctx = document.getElementById('attendanceChart').getContext('2d');
const attendanceChart = new Chart(ctx, {
    type: 'bar',
    data: {
        labels: ['Doctor A', 'Doctor B', 'Doctor C', 'Doctor D'],
        datasets: [{
            label: 'Attendance (Days)',
            data: [20, 18, 25, 22],
            backgroundColor: 'rgba(0, 150, 136, 0.6)',
            borderColor: 'rgba(0, 150, 136, 1)',
            borderWidth: 1
        }]
    },
    options: {
        responsive: true,
        scales: {
            y: {
                beginAtZero: true
            }
        }
    }
});
</script>
