$(document).ready(function(){

    var $symb = $('#symbol')

    $('#symbol').keyup(function(){
        $.ajax({
            type: 'GET',
            url: '/lookup',
            data: {
                symbol: $symb
            },
            success: function(data) {
                $('#sym').html(data);
            },
            error: function() {
                alert('error loading lookupprice');
            }
        });
    });
});

    // <script>
    //     $(document).ready(function(){
    //         var $symb = $('#symbol')
    //         $('#symbol').keyup(function(){
    //             $.ajax({
    //                 type: 'GET',
    //                 url: '/lookup',
    //                 data: {
    //                     symbol: $symb
    //                 },
    //                 success: function(data) {
    //                     $('#symDisplay').html(data);
    //                 },
    //                 error: function() {
    //                     alert('error loading lookupprice');
    //                 }
    //             });
    //         });
    //     });
    // </script>