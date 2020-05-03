$(function (){

    var $symbol = $('#symbol')

    $.ajax({
        type: 'GET',
        url: '/lookup',
        data: {
            symbol: symbol
        },
        success: function(data) {
            $.each(data, function(i, item) {
                $symbol.append(item.price);
            });
        },
        error: function() {
            alert('error loading orders');
        }
    });
});