package portfolio.analytics;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/runs")
class QueryController {
    record CreateQuery(@NotBlank @Size(max = 400) String question) {}

    private final QueryService service;

    QueryController(QueryService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    QueryService.RunView create(@RequestHeader("Idempotency-Key") String key,
                                @RequestBody @Valid CreateQuery input) {
        if (!key.matches("[a-zA-Z0-9_-]{8,80}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "幂等键格式不正确");
        }
        return service.create(key, input.question());
    }

    @GetMapping("/{id}")
    QueryService.RunView get(@PathVariable String id) {
        return service.view(service.require(id));
    }
}
